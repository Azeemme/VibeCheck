import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from api.config import settings
from api.models.assessment import Assessment
from api.models.finding import Finding
from api.services.scanners import (
    config_scanner,
    claude_scanner,
    dependency_scanner,
    pattern_scanner,
    secret_scanner,
)
from api.utils.errors import VibeCheckError


async def run_lightweight_scan(
    assessment_id: str,
    repo_url: str | None,
    files: list[dict] | None,
    db_factory,
    context_limit: int = 50_000,
):
    """
    Main lightweight scan orchestrator.
    db_factory is the async sessionmaker (not a session) since background tasks
    need to create their own sessions.
    """
    async with db_factory() as db:
        assessment = await db.get(Assessment, assessment_id)
        if not assessment:
            return

        all_findings: list[dict] = []

        try:
            if repo_url:
                assessment.status = "cloning"
                await db.commit()
                project_files = await clone_and_read_repo(repo_url, assessment_id)
            else:
                project_files = [
                    {"path": f["path"], "content": f["content"]}
                    for f in (files or [])
                ]

            assessment.status = "analyzing"
            await db.commit()

            project_info = detect_project_info(project_files)

            for f in dependency_scanner.scan(project_files, project_info):
                f.setdefault("agent", "dependency_scanner")
                all_findings.append(f)

            for f in pattern_scanner.scan(project_files):
                f.setdefault("agent", "pattern_scanner")
                all_findings.append(f)

            for f in secret_scanner.scan(project_files):
                f.setdefault("agent", "secret_scanner")
                all_findings.append(f)

            for f in config_scanner.scan(project_files, project_info):
                f.setdefault("agent", "config_scanner")
                all_findings.append(f)

            if settings.GEMINI_API_KEY:
                claude_findings = await claude_scanner.scan(
                    project_files, project_info, max_chars=context_limit
                )

                for f in claude_findings:
                    f.setdefault("agent", "gemini_llm")
                    all_findings.append(f)

            finding_counts = {
                "critical": 0, "high": 0, "medium": 0,
                "low": 0, "info": 0, "total": 0,
            }
            for f in all_findings:
                finding = Finding(
                    assessment_id=assessment_id,
                    severity=f["severity"],
                    category=f["category"],
                    title=f["title"],
                    description=f["description"],
                    location=f.get("location"),
                    evidence=f.get("evidence"),
                    remediation=f["remediation"],
                    agent=f.get("agent", "static_analyzer"),
                )
                db.add(finding)
                finding_counts[f["severity"]] += 1
                finding_counts["total"] += 1

            assessment.finding_counts = finding_counts
            assessment.status = "complete"
            assessment.completed_at = datetime.now(timezone.utc)

            await db.commit()

        except VibeCheckError as e:
            await db.rollback()
            assessment.status = "failed"
            assessment.error_type = e.code
            assessment.error_message = e.message[:500]
            try:
                await db.commit()
            except Exception:
                pass

        except Exception as e:
            await db.rollback()
            assessment.status = "failed"
            assessment.error_type = "SCAN_ERROR"
            assessment.error_message = str(e)[:500]
            try:
                await db.commit()
            except Exception:
                pass

        finally:
            if repo_url:
                cleanup_clone(assessment_id)


CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".html", ".vue", ".svelte", ".sql", ".sh", ".bash",
}
CONFIG_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".env.example",
    ".env.local", ".env.development", ".env.production",
}
CONFIG_FILENAMES = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".gitignore", ".dockerignore", "Makefile", "Procfile",
    "nginx.conf", "next.config.js", "next.config.mjs",
    "vite.config.ts", "vite.config.js", "webpack.config.js",
    "tsconfig.json", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "package.json", "package-lock.json",
    "Cargo.toml", "go.mod", "go.sum", "Gemfile",
}
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".next", ".nuxt",
    "dist", "build", "venv", ".venv", "vendor", "target",
}
ALLOWED_EXTENSIONS = CODE_EXTENSIONS | CONFIG_EXTENSIONS


async def clone_and_read_repo(repo_url: str, assessment_id: str) -> list[dict]:
    """Clone a public GitHub repo and read its files into memory."""
    clone_dir = os.path.join(settings.CLONE_DIR, assessment_id)
    os.makedirs(clone_dir, exist_ok=True)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, clone_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise VibeCheckError.clone_failed(repo_url, result.stderr.strip())
    except subprocess.TimeoutExpired:
        raise VibeCheckError.clone_failed(repo_url, "Clone timed out after 60 seconds")

    files: list[dict] = []
    for root, dirs, filenames in os.walk(clone_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in filenames:
            filepath = os.path.join(root, filename)
            ext = os.path.splitext(filename)[1]
            if ext in ALLOWED_EXTENSIONS or filename in CONFIG_FILENAMES:
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    if len(content) > 100_000:
                        continue
                    rel_path = os.path.relpath(filepath, clone_dir)
                    files.append({"path": rel_path, "content": content})
                except Exception:
                    continue

    return files


def cleanup_clone(assessment_id: str):
    clone_dir = os.path.join(settings.CLONE_DIR, assessment_id)
    shutil.rmtree(clone_dir, ignore_errors=True)


def detect_project_info(files: list[dict]) -> dict:
    """Detect framework, language, and dependency info from project files."""
    info: dict = {
        "language": None,
        "framework": None,
        "dependencies": {},
        "has_gitignore": False,
        "gitignore_entries": [],
    }

    for f in files:
        path = f["path"]
        content = f["content"]

        if path == "package.json" or path.endswith("/package.json"):
            try:
                pkg = json.loads(content)
                info["language"] = "javascript"
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                info["dependencies"].update(deps)
                if "next" in deps:
                    info["framework"] = "nextjs"
                elif "express" in deps:
                    info["framework"] = "express"
                elif "react" in deps:
                    info["framework"] = "react"
                elif "vue" in deps:
                    info["framework"] = "vue"
                elif "@angular/core" in deps:
                    info["framework"] = "angular"
                elif "svelte" in deps:
                    info["framework"] = "svelte"
                elif "fastify" in deps:
                    info["framework"] = "fastify"
                elif "hono" in deps:
                    info["framework"] = "hono"
            except json.JSONDecodeError:
                pass

        elif path == "requirements.txt" or path.endswith("/requirements.txt"):
            info["language"] = "python"
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    for sep in ["==", ">=", "<=", "~=", "!="]:
                        if sep in line:
                            name, ver = line.split(sep, 1)
                            info["dependencies"][name.strip()] = ver.strip()
                            break
                    else:
                        info["dependencies"][line] = "*"

            deps = info["dependencies"]
            if "flask" in deps or "Flask" in deps:
                info["framework"] = "flask"
            elif "django" in deps or "Django" in deps:
                info["framework"] = "django"
            elif "fastapi" in deps:
                info["framework"] = "fastapi"

        elif path == "pyproject.toml" or path.endswith("/pyproject.toml"):
            info["language"] = info["language"] or "python"
            for line in content.splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("[") and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        key = parts[0].strip().strip('"')
                        val = parts[1].strip().strip('"').strip("'")
                        if any(c in val for c in "0123456789.><=~^"):
                            info["dependencies"][key] = val

        elif path == "go.mod" or path.endswith("/go.mod"):
            info["language"] = "go"
            info["framework"] = "go"

        elif path == "Cargo.toml" or path.endswith("/Cargo.toml"):
            info["language"] = "rust"

        elif path == ".gitignore" or path.endswith("/.gitignore"):
            info["has_gitignore"] = True
            info["gitignore_entries"] = [
                line.strip()
                for line in content.splitlines()
                if line.strip() and not line.startswith("#")
            ]

    if not info["language"]:
        ext_counts: dict[str, int] = {}
        for f in files:
            ext = os.path.splitext(f["path"])[1]
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php", ".java": "java",
        }
        if ext_counts:
            top_ext = max(ext_counts, key=ext_counts.get)
            info["language"] = ext_map.get(top_ext, "unknown")

    return info
