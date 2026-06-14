import sys
import os
sys.path.insert(0, '/home/vision/projects/people-analytics')

from flask import Flask, render_template_string, jsonify, send_from_directory, abort
from shared.database import get_current_ad
from shared.config import (
    AD_MEDIA_DIR, AD_SLIDE_SECS, AD_POLL_SECS,
    AD_VIEWER_HOST, AD_VIEWER_PORT,
)

app = Flask(__name__)

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')


def list_categories():
    """Subfolder names under AD_MEDIA_DIR that contain at least one image."""
    if not os.path.isdir(AD_MEDIA_DIR):
        return []
    cats = []
    for name in sorted(os.listdir(AD_MEDIA_DIR)):
        full = os.path.join(AD_MEDIA_DIR, name)
        if os.path.isdir(full) and list_images(name):
            cats.append(name)
    return cats


def list_images(category):
    """Image filenames (sorted) inside AD_MEDIA_DIR/<category>."""
    folder = os.path.join(AD_MEDIA_DIR, category)
    if not os.path.isdir(folder):
        return []
    return sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith(IMAGE_EXTS)
    )


@app.route('/')
def index():
    return render_template_string(
        VIEWER_HTML,
        slide_secs=AD_SLIDE_SECS,
        poll_secs=AD_POLL_SECS,
    )


@app.route('/api/current_ad')
def api_current_ad():
    ad = get_current_ad()
    category = ad['ad_category']

    images = list_images(category)
    fallback_used = False

    if not images:
        # No images for this category — fall back to "default"
        images = list_images('default')
        fallback_used = True
        category_served = 'default'
    else:
        category_served = category

    return jsonify({
        'ad_category': ad['ad_category'],
        'category_served': category_served,
        'fallback_used': fallback_used,
        'dominant_age': ad['dominant_age'],
        'dominant_gender': ad['dominant_gender'],
        'timestamp': ad['timestamp'],
        'images': [f'/ads/{category_served}/{f}' for f in images],
        'available_categories': list_categories(),
    })


@app.route('/ads/<category>/<filename>')
def serve_ad_image(category, filename):
    folder = os.path.join(AD_MEDIA_DIR, category)
    if not os.path.isdir(folder):
        abort(404)
    if filename not in list_images(category):
        abort(404)
    return send_from_directory(folder, filename)


VIEWER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ad Viewer</title>
<style>
  :root {
    --bg: #0c0d10;
    --text: #e8e6e1;
    --text-dim: #6b7280;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100%; height: 100%;
    background: var(--bg);
    overflow: hidden;
    font-family: 'IBM Plex Sans', Arial, sans-serif;
  }
  .stage {
    position: relative;
    width: 100vw; height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .slide {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.8s ease;
  }
  .slide.active { opacity: 1; }
  .slide img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  .placeholder {
    color: var(--text-dim);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 16px;
    text-align: center;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .badge {
    position: absolute;
    bottom: 18px;
    right: 18px;
    background: rgba(0,0,0,0.5);
    color: var(--text-dim);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 6px 12px;
    border-radius: 4px;
    z-index: 10;
  }
</style>
</head>
<body>
<div class="stage" id="stage">
  <div class="placeholder">Loading ad content&hellip;</div>
</div>
<div class="badge" id="badge"></div>

<script>
const SLIDE_SECS = {{ slide_secs }};
const POLL_SECS  = {{ poll_secs }};

let currentCategory = null;
let images = [];
let slideIndex = 0;
let slideTimer = null;

const stage = document.getElementById('stage');
const badge = document.getElementById('badge');

function renderSlides() {
  stage.innerHTML = '';
  if (!images.length) {
    stage.innerHTML = '<div class="placeholder">No ad content for "' + (currentCategory || 'default') + '"<br>Add images to adviewer/ads/' + (currentCategory || 'default') + '/</div>';
    return;
  }
  images.forEach((src, i) => {
    const div = document.createElement('div');
    div.className = 'slide' + (i === 0 ? ' active' : '');
    const img = document.createElement('img');
    img.src = src;
    div.appendChild(img);
    stage.appendChild(div);
  });
  slideIndex = 0;
}

function advanceSlide() {
  if (!images.length) return;
  const slides = stage.querySelectorAll('.slide');
  slides[slideIndex].classList.remove('active');
  slideIndex = (slideIndex + 1) % images.length;
  slides[slideIndex].classList.add('active');
}

function startSlideshow() {
  if (slideTimer) clearInterval(slideTimer);
  slideTimer = setInterval(advanceSlide, SLIDE_SECS * 1000);
}

function refresh() {
  fetch('/api/current_ad')
    .then(r => r.json())
    .then(data => {
      const newImages = data.images;
      const changed = (
        data.category_served !== currentCategory ||
        newImages.length !== images.length ||
        newImages.some((src, i) => src !== images[i])
      );

      currentCategory = data.category_served;
      images = newImages;

      let label = data.ad_category.replace(/_/g, ' ').toUpperCase();
      if (data.dominant_gender && data.dominant_age) {
        label += ' \u2014 ' + data.dominant_gender + ', ' + data.dominant_age;
      }
      badge.textContent = label;

      if (changed) {
        renderSlides();
        startSlideshow();
      }
    })
    .catch(() => {
      badge.textContent = 'OFFLINE';
    });
}

refresh();
setInterval(refresh, POLL_SECS * 1000);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print(f"[AdViewer] Serving ads from: {AD_MEDIA_DIR}")
    print(f"[AdViewer] Starting at http://{AD_VIEWER_HOST}:{AD_VIEWER_PORT}")
    app.run(host=AD_VIEWER_HOST, port=AD_VIEWER_PORT, debug=False)
