import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path("assets_docker_guide/visuals")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Fonts
try:
    FONT_TITLE = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 46)
    FONT_SUBTITLE = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 26)
    FONT_HEAD = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32)
    FONT_BODY = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 24)
    FONT_BOLD = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28)
    FONT_CODE = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 24)
    FONT_CODE_BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 26)
except Exception:
    FONT_TITLE = FONT_SUBTITLE = FONT_HEAD = FONT_BODY = FONT_BOLD = FONT_CODE = FONT_CODE_BOLD = ImageFont.load_default()

def draw_background(draw, width=1920, height=1080):
    # Dark modern slate gradient base
    draw.rectangle([0, 0, width, height], fill="#0a0f1d")
    # Draw subtle ambient glow in center
    for r in range(400, 0, -20):
        alpha = int(25 * (1.0 - r / 400.0))
        glow_box = [width//2 - r, height//2 - r, width//2 + r, height//2 + r]
        draw.ellipse(glow_box, outline=(14, 165, 233, alpha), width=3)

    # Grid dots
    for x in range(60, width, 80):
        for y in range(60, height, 80):
            draw.point((x, y), fill=(30, 41, 59))

def draw_rounded_card(draw, box, fill, outline=None, width=1, radius=16):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

# -------------------------------------------------------------
# Graphic 1: Docker Layers Stack (04_docker_layers_stack.png)
# -------------------------------------------------------------
def render_layers():
    img = Image.new("RGBA", (1920, 1080), "#0a0f1d")
    draw = ImageDraw.Draw(img)
    draw_background(draw)

    # Header
    draw.text((960, 80), "DOCKER IMAGE & CONTAINER LAYERS", fill="#00E5FF", font=FONT_TITLE, anchor="mm")
    draw.text((960, 130), "Immutable Read-Only Base Layers + Thin Writable Container Layer", fill="#94A3B8", font=FONT_SUBTITLE, anchor="mm")

    layers = [
        {
            "title": "TOP LAYER: Writable Container Layer (R/W)",
            "desc": "Container-specific temporary storage (File changes, runtime logs). Ephemeral.",
            "code": "docker run --name api-service",
            "accent": "#10B981", # Emerald
            "bg": "#064e3b",
            "is_writable": True
        },
        {
            "title": "LAYER 3: Application Source Code (Read-Only)",
            "desc": "Transferred code and static assets into the image.",
            "code": "COPY . /app",
            "accent": "#06B6D4", # Cyan
            "bg": "#164e63",
            "is_writable": False
        },
        {
            "title": "LAYER 2: Dependencies & Runtime Environment (Read-Only)",
            "desc": "Installed libraries, package managers, and binaries. Cached automatically.",
            "code": "RUN pip install --no-cache-dir -r requirements.txt",
            "accent": "#8B5CF6", # Purple
            "bg": "#3b0764",
            "is_writable": False
        },
        {
            "title": "BASE LAYER: Operating System Foundation (Read-Only)",
            "desc": "Minimal root filesystem (e.g. Alpine Linux, Debian Slim, Ubuntu). Shared across containers.",
            "code": "FROM python:3.11-slim",
            "accent": "#3B82F6", # Blue
            "bg": "#1e3a8a",
            "is_writable": False
        }
    ]

    card_w = 1100
    card_h = 135
    start_x = (1920 - card_w) // 2
    start_y = 210
    gap = 25

    for i, l in enumerate(layers):
        y = start_y + i * (card_h + gap)
        # Glow border for writable layer
        if l["is_writable"]:
            draw_rounded_card(draw, [start_x - 4, y - 4, start_x + card_w + 4, y + card_h + 4], fill="#10B981", radius=18)
        
        draw_rounded_card(draw, [start_x, y, start_x + card_w, y + card_h], fill="#111827", outline=l["accent"], width=2, radius=14)

        # Badge
        badge_text = "WRITABLE (READ/WRITE)" if l["is_writable"] else "IMMUTABLE (READ-ONLY)"
        draw_rounded_card(draw, [start_x + 25, y + 22, start_x + 260, y + 54], fill=l["bg"], outline=l["accent"], width=1, radius=6)
        draw.text((start_x + 142, y + 37), badge_text, fill=l["accent"], font=FONT_CODE_BOLD, anchor="mm")

        # Title
        draw.text((start_x + 280, y + 25), l["title"], fill="#F8FAFC", font=FONT_BOLD)
        # Description
        draw.text((start_x + 280, y + 62), l["desc"], fill="#94A3B8", font=FONT_BODY)
        # Code box on right
        draw_rounded_card(draw, [start_x + 25, y + 75, start_x + 260, y + 115], fill="#030712", outline="#334155", width=1, radius=6)
        draw.text((start_x + 142, y + 95), l["code"][:22], fill="#E2E8F0", font=FONT_CODE, anchor="mm")

        # Full code display
        draw.text((start_x + 280, y + 95), f"Dockerfile: {l['code']}", fill=l["accent"], font=FONT_CODE)

    # Footer highlights
    draw.text((960, 920), "⚡ Near-Zero Overhead: Multiple containers share the exact same underlying read-only layers!", fill="#38BDF8", font=FONT_HEAD, anchor="mm")

    img.save(OUT_DIR / "04_docker_layers_stack.png", "PNG")
    print("Generated 04_docker_layers_stack.png")

# -------------------------------------------------------------
# Graphic 2: Terminal & Dockerfile (05_terminal_dockerfile.png)
# -------------------------------------------------------------
def render_terminal():
    img = Image.new("RGBA", (1920, 1080), "#0a0f1d")
    draw = ImageDraw.Draw(img)
    draw_background(draw)

    # Header
    draw.text((960, 70), "DOCKERFILE TO RUNNING CONTAINER IN SECONDS", fill="#00E5FF", font=FONT_TITLE, anchor="mm")
    draw.text((960, 120), "Automated, Reproducible, Zero Environment Drift", fill="#94A3B8", font=FONT_SUBTITLE, anchor="mm")

    # Left Card: Dockerfile Code
    lx1, ly1, lx2, ly2 = 120, 180, 900, 960
    draw_rounded_card(draw, [lx1, ly1, lx2, ly2], fill="#0F172A", outline="#38BDF8", width=2, radius=16)

    # Terminal buttons
    draw.ellipse([lx1 + 25, ly1 + 22, lx1 + 41, ly1 + 38], fill="#EF4444")
    draw.ellipse([lx1 + 50, ly1 + 22, lx1 + 66, ly1 + 38], fill="#F59E0B")
    draw.ellipse([lx1 + 75, ly1 + 22, lx1 + 91, ly1 + 38], fill="#10B981")
    draw.text((lx1 + 120, ly1 + 20), "Dockerfile — app-service", fill="#94A3B8", font=FONT_BOLD)

    dockerfile_lines = [
        ("# Base image with Python 3.11 runtime", "#64748B"),
        ("FROM python:3.11-slim", "#38BDF8"),
        ("", "#000000"),
        ("# Set working directory", "#64748B"),
        ("WORKDIR /usr/src/app", "#F8FAFC"),
        ("", "#000000"),
        ("# Cache dependencies layer", "#64748B"),
        ("COPY requirements.txt ./", "#F8FAFC"),
        ("RUN pip install --no-cache-dir -r requirements.txt", "#A855F7"),
        ("", "#000000"),
        ("# Copy application source code", "#64748B"),
        ("COPY . .", "#F8FAFC"),
        ("", "#000000"),
        ("# Expose microservice port", "#64748B"),
        ("EXPOSE 8000", "#F59E0B"),
        ("", "#000000"),
        ("# Start application server", "#64748B"),
        ('CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]', "#10B981")
    ]

    cur_y = ly1 + 80
    for line, color in dockerfile_lines:
        if line:
            draw.text((lx1 + 40, cur_y), line, fill=color, font=FONT_CODE_BOLD)
        cur_y += 36

    # Right Card: CLI Execution
    rx1, ry1, rx2, ry2 = 940, 180, 1800, 960
    draw_rounded_card(draw, [rx1, ry1, rx2, ry2], fill="#0F172A", outline="#10B981", width=2, radius=16)

    # Terminal buttons
    draw.ellipse([rx1 + 25, ry1 + 22, rx1 + 41, ry1 + 38], fill="#EF4444")
    draw.ellipse([rx1 + 50, ry1 + 22, rx1 + 66, ry1 + 38], fill="#F59E0B")
    draw.ellipse([rx1 + 75, ry1 + 22, rx1 + 91, ry1 + 38], fill="#10B981")
    draw.text((rx1 + 120, ry1 + 20), "bash — docker run", fill="#94A3B8", font=FONT_BOLD)

    cli_lines = [
        ("$ docker build -t my-app:latest .", "#00E5FF"),
        ("[+] Building 1.2s (8/8) FINISHED", "#94A3B8"),
        (" => [internal] load build definition from Dockerfile", "#64748B"),
        (" => CACHED [2/4] WORKDIR /usr/src/app", "#10B981"),
        (" => CACHED [3/4] COPY requirements.txt ./", "#10B981"),
        (" => CACHED [4/4] RUN pip install --no-cache-dir", "#10B981"),
        (" => exporting to image: docker.io/library/my-app:latest", "#38BDF8"),
        ("", "#000000"),
        ("$ docker run -d -p 8000:8000 --name api my-app", "#00E5FF"),
        ("7c4b8e9102ab8f72c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8", "#94A3B8"),
        ("", "#000000"),
        ("$ docker ps", "#00E5FF"),
        ("CONTAINER ID   IMAGE      STATUS         PORTS", "#94A3B8"),
        ("7c4b8e9102ab   my-app     Up 2 seconds   0.0.0.0:8000->8000", "#10B981"),
        ("", "#000000"),
        ("✓ HEALTHCHECK: API ONLINE & RESPONDING IN 12ms", "#10B981")
    ]

    cur_y = ry1 + 80
    for line, color in cli_lines:
        if line:
            draw.text((rx1 + 40, cur_y), line, fill=color, font=FONT_CODE_BOLD)
        cur_y += 38

    img.save(OUT_DIR / "05_terminal_dockerfile.png", "PNG")
    print("Generated 05_terminal_dockerfile.png")

# -------------------------------------------------------------
# Graphic 3: Summary Takeaways (06_final_takeaway.png)
# -------------------------------------------------------------
def render_takeaways():
    img = Image.new("RGBA", (1920, 1080), "#0a0f1d")
    draw = ImageDraw.Draw(img)
    draw_background(draw)

    # Header
    draw.text((960, 80), "THE VERDICT: CONTAINERS vs VIRTUAL MACHINES", fill="#00E5FF", font=FONT_TITLE, anchor="mm")
    draw.text((960, 130), "Why Containers Dominate Modern Cloud & Microservices", fill="#94A3B8", font=FONT_SUBTITLE, anchor="mm")

    cards = [
        {
            "metric": "STARTUP TIME",
            "vm": "1 to 5 Minutes",
            "vm_sub": "Full OS boot sequence",
            "container": "50 to 200 Milliseconds",
            "container_sub": "Instant process instantiation",
            "winner": "100x Faster"
        },
        {
            "metric": "STORAGE FOOTPRINT",
            "vm": "10 to 50 Gigabytes",
            "vm_sub": "Heavy kernel & OS binaries",
            "container": "20 to 150 Megabytes",
            "container_sub": "Shared base layers & thin diffs",
            "winner": "95% Smaller"
        },
        {
            "metric": "RESOURCE OVERHEAD",
            "vm": "Dedicated CPU & RAM",
            "vm_sub": "Hypervisor abstraction cost",
            "container": "Near-Native Performance",
            "container_sub": "Direct Linux kernel execution",
            "winner": "Zero Waste"
        },
        {
            "metric": "PORTABILITY",
            "vm": "Complex VM Export",
            "vm_sub": "Host-dependent formats",
            "container": "Runs Identically Anywhere",
            "container_sub": "Standard OCI Image Specification",
            "winner": "Universal"
        }
    ]

    start_y = 200
    card_h = 145
    gap = 25
    w = 1200
    x1 = (1920 - w) // 2
    x2 = x1 + w

    for i, c in enumerate(cards):
        y = start_y + i * (card_h + gap)
        draw_rounded_card(draw, [x1, y, x2, y + card_h], fill="#111827", outline="#334155", width=2, radius=14)

        # Metric name on left
        draw_rounded_card(draw, [x1 + 20, y + 20, x1 + 300, y + card_h - 20], fill="#1E293B", outline="#38BDF8", width=1, radius=10)
        draw.text((x1 + 160, y + card_h // 2), c["metric"], fill="#00E5FF", font=FONT_HEAD, anchor="mm")

        # VM Column
        draw.text((x1 + 350, y + 45), f"VM: {c['vm']}", fill="#F87171", font=FONT_BOLD)
        draw.text((x1 + 350, y + 85), c["vm_sub"], fill="#94A3B8", font=FONT_BODY)

        # Arrow / VS
        draw.text((x1 + 730, y + card_h // 2), "➔", fill="#38BDF8", font=FONT_TITLE, anchor="mm")

        # Container Column
        draw.text((x1 + 790, y + 45), f"Docker: {c['container']}", fill="#34D399", font=FONT_BOLD)
        draw.text((x1 + 790, y + 85), c["container_sub"], fill="#94A3B8", font=FONT_BODY)

        # Badge on right
        draw_rounded_card(draw, [x2 - 180, y + 45, x2 - 25, y + 105], fill="#064e3b", outline="#10B981", width=1, radius=8)
        draw.text((x2 - 102, y + 75), c["winner"], fill="#34D399", font=FONT_BOLD, anchor="mm")

    # Bottom Call to Action
    draw.text((960, 940), "Stop configuring machines. Package your applications once and ship anywhere.", fill="#F8FAFC", font=FONT_HEAD, anchor="mm")

    img.save(OUT_DIR / "06_final_takeaway.png", "PNG")
    print("Generated 06_final_takeaway.png")

if __name__ == "__main__":
    render_layers()
    render_terminal()
    render_takeaways()
