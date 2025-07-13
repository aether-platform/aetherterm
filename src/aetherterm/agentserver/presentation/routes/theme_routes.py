"""
Theme Routes - Theme Management Endpoints

Provides theme-related routes for CSS serving and theme management.
"""

import logging
import os
import hashlib
import time
from mimetypes import guess_type
from typing import Dict, Tuple, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from aetherterm.agentserver.infrastructure.common.memoization import memoize, cached_property

# Initialize router
router = APIRouter()
log = logging.getLogger("aetherterm.routes.theme")

# Cache for compiled themes
_theme_cache: Dict[str, Tuple[str, float]] = {}
_THEME_CACHE_TTL = 3600  # 1 hour

@memoize(maxsize=10)
def _get_themes_directory() -> str:
    """Get themes directory path with caching."""
    return os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "themes")

@memoize(maxsize=10)
def _get_builtin_themes_directory() -> str:
    """Get built-in themes directory with caching."""
    return os.path.join(os.path.dirname(__file__), "..", "themes")

@memoize(maxsize=10)
def _get_sass_path() -> str:
    """Get sass path with caching."""
    return os.path.join(os.path.dirname(__file__), "..", "sass")

def _get_theme_cache_key(style_path: str, base_dir: str) -> str:
    """Generate cache key for theme."""
    # Include file modification time in cache key
    mtime = os.path.getmtime(style_path) if os.path.exists(style_path) else 0
    key_string = f"{style_path}:{base_dir}:{mtime}"
    return hashlib.md5(key_string.encode()).hexdigest()

def _get_cached_theme(cache_key: str) -> Optional[str]:
    """Get theme from cache if not expired."""
    if cache_key in _theme_cache:
        css, timestamp = _theme_cache[cache_key]
        if time.time() - timestamp < _THEME_CACHE_TTL:
            return css
        else:
            del _theme_cache[cache_key]
    return None

def _cache_theme(cache_key: str, css: str) -> None:
    """Cache compiled theme CSS."""
    _theme_cache[cache_key] = (css, time.time())
    # Limit cache size
    if len(_theme_cache) > 50:
        # Remove oldest entries
        sorted_items = sorted(_theme_cache.items(), key=lambda x: x[1][1])
        for key, _ in sorted_items[:10]:
            del _theme_cache[key]

@memoize(maxsize=100)
def _has_style_file(theme_path: str) -> bool:
    """Check if theme has style file with caching."""
    return any(
        os.path.exists(os.path.join(theme_path, f"style.{ext}"))
        for ext in ["css", "scss", "sass"]
    )


@router.get("/theme/{theme}/style.css")
async def theme_style(theme: str):
    """Serve theme CSS files."""
    try:
        import sass
    except ImportError:
        log.error("You must install libsass to use sass (pip install libsass)")
        raise HTTPException(status_code=500, detail="Sass compiler not available")

    # Get theme directory with caching
    themes_dir = _get_themes_directory()
    builtin_themes_dir = _get_builtin_themes_directory()

    base_dir = None
    if theme.startswith("built-in-"):
        theme_name = theme[9:]  # Remove 'built-in-' prefix
        base_dir = os.path.join(builtin_themes_dir, theme_name)
    else:
        base_dir = os.path.join(themes_dir, theme)

    if not os.path.exists(base_dir):
        raise HTTPException(status_code=404, detail="Theme not found")

    # Look for style file
    style = None
    for ext in ["css", "scss", "sass"]:
        probable_style = os.path.join(base_dir, f"style.{ext}")
        if os.path.exists(probable_style):
            style = probable_style
            break

    if not style:
        raise HTTPException(status_code=404, detail="Style file not found")

    # Check cache first
    cache_key = _get_theme_cache_key(style, base_dir)
    cached_css = _get_cached_theme(cache_key)
    if cached_css:
        log.debug(f"Serving cached theme: {theme}")
        return Response(content=cached_css, media_type="text/css")
    
    # Compile sass if not cached
    sass_path = _get_sass_path()

    try:
        css = sass.compile(filename=style, include_paths=[base_dir, sass_path])
        # Cache the compiled CSS
        _cache_theme(cache_key, css)
        return Response(content=css, media_type="text/css")
    except Exception as e:
        log.error(f"Unable to compile style: {e}")
        raise HTTPException(status_code=500, detail="Style compilation failed")


@router.get("/theme/{theme}/{filename:path}")
async def theme_static(theme: str, filename: str):
    """Serve static theme files."""
    if ".." in filename:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get theme directory with caching
    themes_dir = _get_themes_directory()
    builtin_themes_dir = _get_builtin_themes_directory()

    base_dir = None
    if theme.startswith("built-in-"):
        theme_name = theme[9:]  # Remove 'built-in-' prefix
        base_dir = os.path.join(builtin_themes_dir, theme_name)
    else:
        base_dir = os.path.join(themes_dir, theme)

    file_path = os.path.normpath(os.path.join(base_dir, filename))

    # Security check
    if not file_path.startswith(base_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_type = guess_type(file_path)[0]
    if content_type is None:
        # Fallback content types
        ext = filename.split(".")[-1].lower()
        content_type = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "woff": "application/font-woff",
            "ttf": "application/x-font-ttf",
        }.get(ext, "text/plain")

    return FileResponse(file_path, media_type=content_type)


@router.get("/themes/list.json")
async def themes_list():
    """Get the list of available themes."""
    themes_dir = os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "themes")
    builtin_themes_dir = os.path.join(os.path.dirname(__file__), "..", "themes")

    themes = []
    if os.path.exists(themes_dir):
        themes = [
            theme
            for theme in os.listdir(themes_dir)
            if os.path.isdir(os.path.join(themes_dir, theme)) and not theme.startswith(".")
        ]

    builtin_themes = []
    if os.path.exists(builtin_themes_dir):
        builtin_themes = [
            f"built-in-{theme}"
            for theme in os.listdir(builtin_themes_dir)
            if os.path.isdir(os.path.join(builtin_themes_dir, theme)) and not theme.startswith(".")
        ]

    return JSONResponse(
        {
            "themes": sorted(themes),
            "builtin_themes": sorted(builtin_themes),
            "dir": themes_dir,
        }
    )
