import os
import math
import wave
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = r"c:\Users\F\Documents\AI Projects\video-editor\build\sinking_car_assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

FONTS_DIR = r"c:\Users\F\Documents\AI Projects\video-editor\assets\fonts"
FONT_BEBAS = os.path.join(FONTS_DIR, "BebasNeue-Regular.ttf")
FONT_TIKTOK = os.path.join(FONTS_DIR, "TikTokSans[opsz,slnt,wdth,wght].ttf")
FONT_MONTSERRAT = os.path.join(FONTS_DIR, "Montserrat[wght].ttf")
FONT_ARCHIVO = os.path.join(FONTS_DIR, "ArchivoBlack-Regular.ttf")

WIDTH, HEIGHT = 1080, 1920

def get_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def create_base_canvas(accent="#06B6D4"):
    im = Image.new("RGBA", (WIDTH, HEIGHT), (10, 14, 26, 255))
    draw = ImageDraw.Draw(im)
    
    # Subtle dark background texture / grid
    for y in range(0, HEIGHT, 80):
        draw.line([(0, y), (WIDTH, y)], fill=(20, 27, 45, 120), width=1)
    for x in range(0, WIDTH, 80):
        draw.line([(x, 0), (x, HEIGHT)], fill=(20, 27, 45, 120), width=1)
        
    # Vertical gradient darkening at bottom
    for y in range(0, HEIGHT, 8):
        alpha = int(90 * (y / HEIGHT))
        draw.rectangle([0, y, WIDTH, y+8], fill=(4, 7, 16, alpha))
        
    # Border & HUD corners
    draw.rectangle([35, 35, WIDTH-35, HEIGHT-35], outline=(35, 45, 69, 255), width=2)
    b_len = 55
    corners = [(35, 35), (WIDTH-35, 35), (35, HEIGHT-35), (WIDTH-35, HEIGHT-35)]
    for cx, cy in corners:
        dx = 1 if cx == 35 else -1
        dy = 1 if cy == 35 else -1
        draw.line([(cx, cy), (cx + dx * b_len, cy)], fill=accent, width=6)
        draw.line([(cx, cy), (cx, cy + dy * b_len)], fill=accent, width=6)
        
    return im, draw

def draw_header(draw, title, subtitle=None, category="SURVIVAL PROTOCOL", badge_color="#EF4444"):
    # Category badge
    bbox = [70, 95, 480, 155]
    draw.rounded_rectangle(bbox, radius=14, fill=badge_color)
    f_badge = get_font(FONT_BEBAS, 38)
    draw.text((95, 103), f"/// {category} ///", fill="#FFFFFF", font=f_badge)
    
    # Title
    f_title = get_font(FONT_BEBAS, 90)
    draw.text((70, 175), title, fill="#FFFFFF", font=f_title)
    
    if subtitle:
        f_sub = get_font(FONT_TIKTOK, 34)
        draw.text((70, 275), subtitle, fill="#94A3B8", font=f_sub)

# ==============================================================================
# CARD 1: WATER PRESSURE DIAGRAM (04)
# ==============================================================================
def make_card_water_pressure():
    im, draw = create_base_canvas(accent="#EF4444")
    draw_header(draw, "THE FATAL MISTAKE", "WHY PUSHING THE DOOR WILL GET YOU KILLED", "CRITICAL WARNING", "#EF4444")
    
    # Main Warning Card
    draw.rounded_rectangle([70, 360, WIDTH-70, 1020], radius=24, fill=(23, 29, 45, 230), outline="#EF4444", width=3)
    
    f_huge = get_font(FONT_BEBAS, 110)
    f_bold = get_font(FONT_BEBAS, 54)
    f_sub = get_font(FONT_TIKTOK, 36)
    f_desc = get_font(FONT_TIKTOK, 32)
    
    draw.text((110, 395), "OUTSIDE WATER PRESSURE", fill="#EF4444", font=f_bold)
    draw.text((110, 460), "3,600+ LBS", fill="#FFFFFF", font=f_huge)
    draw.text((110, 580), "OF BRUTE FORCE AGAINST THE CAR DOOR", fill="#CBD5E1", font=f_sub)
    
    # Inward Force Arrows
    arrow_y = 660
    for i in range(4):
        ax = 140 + i * 220
        draw.polygon([(ax+40, arrow_y), (ax+40, arrow_y+50), (ax+80, arrow_y+50), (ax+80, arrow_y+75), (ax+120, arrow_y+25), (ax+80, arrow_y-25), (ax+80, arrow_y), (ax+40, arrow_y)], fill="#EF4444")
        draw.text((ax+20, arrow_y+90), "WATER", fill="#EF4444", font=get_font(FONT_BEBAS, 28))
        
    # Pressure breakdown
    draw.rounded_rectangle([100, 810, WIDTH-100, 980], radius=16, fill=(35, 15, 20, 200), outline="#EF4444", width=2)
    draw.text((130, 835), "CALCULATION: 10 SQ FT DOOR × 2.5 PSI WATER DEPTH", fill="#FECACA", font=get_font(FONT_BEBAS, 36))
    draw.text((130, 895), "= EQUIVALENT TO PUSHING AGAINST A SOLID CONCRETE WALL", fill="#F87171", font=f_desc)

    # Bottom Big Banner
    draw.rounded_rectangle([70, 1060, WIDTH-70, 1340], radius=24, fill=(185, 28, 28, 240), outline="#FCA5A5", width=3)
    draw.text((120, 1100), "DO NOT TOUCH THE DOOR", fill="#FFFFFF", font=get_font(FONT_BEBAS, 78))
    draw.text((120, 1195), "You will exhaust your oxygen in seconds.", fill="#FFFFFF", font=f_sub)
    draw.text((120, 1245), "Doors cannot open until the car completely fills.", fill="#FEE2E2", font=f_desc)
    
    # Golden alternative hint
    draw.rounded_rectangle([70, 1380, WIDTH-70, 1680], radius=24, fill=(15, 23, 42, 230), outline="#06B6D4", width=3)
    draw.text((120, 1420), "INSTEAD: FOCUS ON WINDOWS", fill="#06B6D4", font=f_bold)
    draw.text((120, 1490), "Water does NOT block side windows from opening.", fill="#E2E8F0", font=f_sub)
    draw.text((120, 1550), "You have 30 to 60 seconds before electrics fail.", fill="#38BDF8", font=f_desc)
    
    path = os.path.join(ASSETS_DIR, "visual_water_pressure_diagram.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 2: SWO GOLDEN SURVIVAL RULE (05)
# ==============================================================================
def make_card_swo():
    im, draw = create_base_canvas(accent="#F59E0B")
    draw_header(draw, "THE SURVIVAL FORMULA", "THE ACCREDITED S-W-O EVACUATION PROTOCOL", "CORE PROTOCOL", "#F59E0B")
    
    # 3 Glowing Steps
    steps = [
        ("S", "SEATBELT", "UNBUCKLE IMMEDIATELY", "Do not touch your phone. Free yourself and kids.", "#EF4444"),
        ("W", "WINDOW", "ROLL DOWN OR BREAK", "Electrics work for 30-60s. Escape path.", "#F59E0B"),
        ("O", "OUT", "CLIMB OUT HEAD-FIRST", "Push children ahead of you. Swim to surface.", "#10B981")
    ]
    
    start_y = 360
    for i, (letter, title, action, desc, col) in enumerate(steps):
        sy = start_y + i * 360
        # Container
        draw.rounded_rectangle([70, sy, WIDTH-70, sy+320], radius=24, fill=(18, 24, 38, 230), outline=col, width=3)
        # Letter Box
        draw.rounded_rectangle([100, sy+30, 240, sy+170], radius=18, fill=col)
        draw.text((135, sy+35), letter, fill="#FFFFFF", font=get_font(FONT_BEBAS, 115))
        
        # Details
        draw.text((270, sy+35), title, fill=col, font=get_font(FONT_BEBAS, 56))
        draw.text((270, sy+100), action, fill="#FFFFFF", font=get_font(FONT_BEBAS, 44))
        draw.text((110, sy+210), desc, fill="#94A3B8", font=get_font(FONT_TIKTOK, 34))
        
    # Bottom Gauge
    draw.rounded_rectangle([70, 1480, WIDTH-70, 1720], radius=20, fill=(30, 41, 59, 220), outline="#64748B", width=2)
    draw.text((110, 1520), "SURVIVAL WINDOW: UNDER 60 SECONDS", fill="#F8FAFC", font=get_font(FONT_BEBAS, 46))
    draw.text((110, 1585), "Panic is your greatest enemy. Execute S-W-O systematically.", fill="#94A3B8", font=get_font(FONT_TIKTOK, 32))
    draw.text((110, 1635), "Recommended by Dr. Gordon Giesbrecht (Operation ALIVE)", fill="#38BDF8", font=get_font(FONT_TIKTOK, 28))

    path = os.path.join(ASSETS_DIR, "visual_swo_golden_rule.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 3: STEP 1 SEATBELT (06)
# ==============================================================================
def make_card_seatbelt():
    im, draw = create_base_canvas(accent="#EF4444")
    draw_header(draw, "STEP 1: SEATBELTS OFF", "IMMEDIATE ACTION BEFORE CAR FLOODS", "ACTION 01", "#EF4444")
    
    # Main visual card
    draw.rounded_rectangle([70, 360, WIDTH-70, 1100], radius=24, fill=(20, 24, 38, 240), outline="#EF4444", width=3)
    
    # Red Release Button Graphic
    draw.rounded_rectangle([240, 420, WIDTH-240, 680], radius=30, fill="#DC2626", outline="#FCA5A5", width=4)
    draw.text((360, 480), "PRESS", fill="#FFFFFF", font=get_font(FONT_BEBAS, 110))
    draw.text((350, 580), "RELEASE", fill="#FFFFFF", font=get_font(FONT_BEBAS, 70))
    
    draw.text((110, 740), "PRESS THE RED BUCKLE RELEASE", fill="#FFFFFF", font=get_font(FONT_BEBAS, 56))
    draw.text((110, 810), "Do this in the first 5 seconds of entering the water.", fill="#94A3B8", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 860), "If it jams, cut it or slip out under the shoulder strap.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 32))
    
    # Phone Warning Box
    draw.rounded_rectangle([70, 1140, WIDTH-70, 1680], radius=24, fill=(40, 10, 15, 230), outline="#EF4444", width=3)
    draw.text((110, 1180), "CRITICAL MISTAKE: DO NOT CALL 911", fill="#EF4444", font=get_font(FONT_BEBAS, 54))
    draw.text((110, 1260), "• Dialing and connecting takes 20 to 40 seconds.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1320), "• In 40 seconds, the car can submerge completely.", fill="#FCA5A5", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1380), "• Rescuers CANNOT arrive before the car sinks.", fill="#FCA5A5", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1460), "RULE: Escape the car FIRST. Call 911 once on land.", fill="#38BDF8", font=get_font(FONT_TIKTOK, 36))

    path = os.path.join(ASSETS_DIR, "visual_step1_seatbelt.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 4: CHILDREN FIRST PROTOCOL (07)
# ==============================================================================
def make_card_children():
    im, draw = create_base_canvas(accent="#F59E0B")
    draw_header(draw, "CHILDREN EVACUATION", "HOW TO RESCUE PASSENGERS RAPIDLY", "PRIORITY SAFETY", "#F59E0B")
    
    # Priority steps
    draw.rounded_rectangle([70, 360, WIDTH-70, 880], radius=24, fill=(20, 25, 40, 240), outline="#F59E0B", width=3)
    
    draw.text((110, 400), "1. UNBUCKLE OLDEST CHILD FIRST", fill="#F59E0B", font=get_font(FONT_BEBAS, 54))
    draw.text((110, 470), "Why? An older child can help unbuckle younger", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 520), "siblings or follow instructions to move forward.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    
    draw.line([(110, 600), (WIDTH-110, 600)], fill=(45, 55, 75), width=2)
    
    draw.text((110, 640), "2. PUSH CHILDREN TOWARDS FRONT SEAT", fill="#10B981", font=get_font(FONT_BEBAS, 54))
    draw.text((110, 710), "Move them into the front passenger area where the", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 760), "open window provides the fastest escape exit.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    
    # Golden Warning
    draw.rounded_rectangle([70, 940, WIDTH-70, 1680], radius=24, fill=(15, 23, 42, 240), outline="#06B6D4", width=3)
    draw.text((110, 980), "PUSH KIDS OUT AHEAD OF YOU", fill="#06B6D4", font=get_font(FONT_BEBAS, 60))
    draw.text((110, 1060), "• Never exit before your children.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 36))
    draw.text((110, 1120), "• Water currents rushing in will make it impossible", fill="#94A3B8", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1170), "  to swim back inside to retrieve them.", fill="#94A3B8", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1250), "• Push their shoulders through the window.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 36))
    draw.text((110, 1310), "• Instruct them to float / grab the car roof.", fill="#38BDF8", font=get_font(FONT_TIKTOK, 36))
    
    path = os.path.join(ASSETS_DIR, "visual_children_priority.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 5: STEP 2 OPEN WINDOW (08)
# ==============================================================================
def make_card_window():
    im, draw = create_base_canvas(accent="#06B6D4")
    draw_header(draw, "STEP 2: OPEN WINDOW", "POWER WINDOWS WORK LONGER THAN YOU THINK", "ACTION 02", "#06B6D4")
    
    draw.rounded_rectangle([70, 360, WIDTH-70, 1060], radius=24, fill=(16, 26, 44, 240), outline="#06B6D4", width=3)
    
    draw.text((110, 400), "PRESS POWER WINDOW SWITCH DOWN", fill="#06B6D4", font=get_font(FONT_BEBAS, 58))
    draw.text((110, 475), "ELECTRICS DO NOT DIE INSTANTLY", fill="#FFFFFF", font=get_font(FONT_BEBAS, 50))
    
    # Stat box
    draw.rounded_rectangle([110, 560, WIDTH-110, 780], radius=18, fill=(6, 78, 99, 120), outline="#06B6D4", width=2)
    draw.text((140, 590), "SURVIVAL FACT:", fill="#F59E0B", font=get_font(FONT_BEBAS, 40))
    draw.text((140, 640), "Research shows electric windows function for", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((140, 690), "30 to 60 seconds after water entry in most vehicles.", fill="#38BDF8", font=get_font(FONT_TIKTOK, 34))
    
    draw.text((110, 830), "• Roll window fully open before water reaches it.", fill="#F8FAFC", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 890), "• Water will rush in—do NOT panic, this is normal.", fill="#94A3B8", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 950), "• The open window is your ONLY escape hatch.", fill="#10B981", font=get_font(FONT_TIKTOK, 36))

    # Jammed Window Callout
    draw.rounded_rectangle([70, 1120, WIDTH-70, 1680], radius=24, fill=(35, 20, 15, 240), outline="#F59E0B", width=3)
    draw.text((110, 1160), "IF WINDOW IS JAMMED OR DEAD:", fill="#F59E0B", font=get_font(FONT_BEBAS, 54))
    draw.text((110, 1240), "You must SHATTER the side window glass.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 36))
    draw.text((110, 1310), "Do NOT try to kick it with soft shoes.", fill="#FCA5A5", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1370), "Use a concentrated metal impact point.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1460), "SEE NEXT: THE HEADREST TRICK", fill="#38BDF8", font=get_font(FONT_BEBAS, 50))

    path = os.path.join(ASSETS_DIR, "visual_step2_window.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 6: WINDSHIELD WARNING (09)
# ==============================================================================
def make_card_windshield():
    im, draw = create_base_canvas(accent="#EF4444")
    draw_header(draw, "NEVER HIT WINDSHIELD", "LAMINATED GLASS WILL NOT SHATTER", "GLASS FACTS", "#EF4444")
    
    # Split comparison
    # Left / Top: Windshield (Bad)
    draw.rounded_rectangle([70, 360, WIDTH-70, 960], radius=24, fill=(38, 15, 20, 240), outline="#EF4444", width=3)
    draw.rounded_rectangle([110, 395, 230, 465], radius=12, fill="#DC2626")
    draw.text((145, 400), "X", fill="#FFFFFF", font=get_font(FONT_BEBAS, 60))
    draw.text((260, 400), "FRONT WINDSHIELD", fill="#EF4444", font=get_font(FONT_BEBAS, 56))
    draw.text((110, 490), "TYPE: LAMINATED SAFETY GLASS", fill="#FFFFFF", font=get_font(FONT_BEBAS, 44))
    draw.text((110, 560), "• Bound by heavy-duty polyvinyl plastic sheet.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 620), "• Designed to withstand passenger ejections & crashes.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 680), "• Striking it only creates spiderwebs—NEVER breaks.", fill="#FCA5A5", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 770), "RESULT: 100% WASTED ENERGY & LOST TIME", fill="#EF4444", font=get_font(FONT_BEBAS, 42))

    # Right / Bottom: Side Windows (Good)
    draw.rounded_rectangle([70, 1020, WIDTH-70, 1680], radius=24, fill=(15, 35, 28, 240), outline="#10B981", width=3)
    draw.rounded_rectangle([110, 1055, 230, 1125], radius=12, fill="#059669")
    draw.text((150, 1060), "OK", fill="#FFFFFF", font=get_font(FONT_BEBAS, 54))
    draw.text((260, 1060), "SIDE WINDOWS", fill="#10B981", font=get_font(FONT_BEBAS, 56))
    draw.text((110, 1150), "TYPE: TEMPERED SAFETY GLASS", fill="#FFFFFF", font=get_font(FONT_BEBAS, 44))
    draw.text((110, 1220), "• Single heat-treated high-tension glass sheet.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1280), "• High surface tension—brittle under point impacts.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1340), "• Shatters into tiny, safe granular cubes.", fill="#6EE7B7", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1430), "TARGET: ALWAYS STRIKE SIDE WINDOWS", fill="#10B981", font=get_font(FONT_BEBAS, 48))

    path = os.path.join(ASSETS_DIR, "visual_windshield_warning.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 7: HEADREST HACK (10)
# ==============================================================================
def make_card_headrest():
    im, draw = create_base_canvas(accent="#F59E0B")
    draw_header(draw, "THE HEADREST HACK", "YOUR VEHICLE'S SECRET EMERGENCY TOOL", "LIFE HACK", "#F59E0B")
    
    draw.rounded_rectangle([70, 360, WIDTH-70, 1100], radius=24, fill=(20, 26, 42, 240), outline="#F59E0B", width=3)
    
    # Headrest prongs illustration box
    draw.rounded_rectangle([200, 410, WIDTH-200, 710], radius=20, fill=(35, 45, 70, 200), outline="#94A3B8", width=2)
    # Headrest top cushion
    draw.rounded_rectangle([250, 440, WIDTH-250, 550], radius=24, fill="#475569")
    draw.text((370, 470), "HEADREST", fill="#FFFFFF", font=get_font(FONT_BEBAS, 48))
    # Two metal prongs
    draw.rectangle([350, 550, 390, 680], fill="#E2E8F0", outline="#94A3B8")
    draw.rectangle([WIDTH-390, 550, WIDTH-350, 680], fill="#E2E8F0", outline="#94A3B8")
    # Beveled tips
    draw.polygon([(350, 680), (390, 680), (370, 705)], fill="#CBD5E1")
    draw.polygon([(WIDTH-390, 680), (WIDTH-350, 680), (WIDTH-370, 705)], fill="#CBD5E1")
    
    draw.text((110, 760), "DUAL HARDENED STEEL PRONGS", fill="#F59E0B", font=get_font(FONT_BEBAS, 54))
    draw.text((110, 830), "• Press release clip at base of seat headrest.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 890), "• Pull headrest straight up and out.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 950), "• The heavy steel rods concentrate extreme psi.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))

    # Strike advice
    draw.rounded_rectangle([70, 1150, WIDTH-70, 1680], radius=24, fill=(15, 23, 42, 240), outline="#06B6D4", width=3)
    draw.text((110, 1190), "HOW TO BREAK THE WINDOW:", fill="#06B6D4", font=get_font(FONT_BEBAS, 52))
    draw.text((110, 1270), "METHOD A: Wedge prong into window seal gap", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 36))
    draw.text((110, 1325), "at the bottom corner and pull towards you.", fill="#38BDF8", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1400), "METHOD B: Strike the extreme corner firmly", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 36))
    draw.text((110, 1455), "using the pointed metal tip like a hammer.", fill="#38BDF8", font=get_font(FONT_TIKTOK, 34))

    path = os.path.join(ASSETS_DIR, "visual_headrest_hack.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 8: WHERE TO STRIKE CORNER (11)
# ==============================================================================
def make_card_corner():
    im, draw = create_base_canvas(accent="#10B981")
    draw_header(draw, "WHERE TO STRIKE", "MAXIMUM IMPACT LEVERAGE POINT", "TECHNIQUE", "#10B981")
    
    # Schematic Window Box
    draw.rounded_rectangle([120, 360, WIDTH-120, 960], radius=20, fill=(20, 30, 50, 240), outline="#64748B", width=4)
    draw.text((WIDTH//2 - 130, 385), "SIDE WINDOW", fill="#94A3B8", font=get_font(FONT_BEBAS, 38))
    
    # Center = Bad
    draw.ellipse([WIDTH//2 - 70, 600, WIDTH//2 + 70, 740], fill=(185, 28, 28, 180), outline="#EF4444", width=3)
    draw.text((WIDTH//2 - 40, 630), "X", fill="#FFFFFF", font=get_font(FONT_BEBAS, 80))
    draw.text((WIDTH//2 - 100, 755), "CENTER = WEAK LEVERAGE", fill="#EF4444", font=get_font(FONT_BEBAS, 32))
    
    # Bottom Corner = Target
    cx, cy = WIDTH-240, 820
    draw.ellipse([cx-60, cy-60, cx+60, cy+60], fill=(5, 150, 105, 230), outline="#34D399", width=4)
    draw.text((cx-30, cy-45), "HIT", fill="#FFFFFF", font=get_font(FONT_BEBAS, 50))
    draw.text((cx-140, cy-100), "TARGET: BOTTOM CORNER", fill="#10B981", font=get_font(FONT_BEBAS, 36))

    # Explanation cards
    draw.rounded_rectangle([70, 1020, WIDTH-70, 1680], radius=24, fill=(15, 23, 42, 240), outline="#10B981", width=3)
    draw.text((110, 1060), "WHY THE CORNER IS WEAKEST:", fill="#10B981", font=get_font(FONT_BEBAS, 52))
    draw.text((110, 1140), "• Center of glass flexes and absorbs shock.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1200), "• The corner is rigidly supported by the metal frame.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1260), "• Rigid constraint prevents flex -> glass instantly", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1310), "  explodes into thousands of blunt safety granules.", fill="#6EE7B7", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1400), "SAFETY: Tempered glass does NOT produce sharp shards.", fill="#F59E0B", font=get_font(FONT_TIKTOK, 34))

    path = os.path.join(ASSETS_DIR, "visual_glass_strike_corner.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 9: STEP 3 ESCAPE OUT (12)
# ==============================================================================
def make_card_escape():
    im, draw = create_base_canvas(accent="#06B6D4")
    draw_header(draw, "STEP 3: CLIMB OUT", "HEAD-FIRST EVACUATION PROTOCOL", "ACTION 03", "#06B6D4")
    
    draw.rounded_rectangle([70, 360, WIDTH-70, 1050], radius=24, fill=(18, 28, 46, 240), outline="#06B6D4", width=3)
    
    draw.text((110, 400), "CLIMB OUT HEAD-FIRST", fill="#06B6D4", font=get_font(FONT_BEBAS, 60))
    draw.text((110, 480), "• Hold window frame with both hands firmly.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 36))
    draw.text((110, 545), "• Pull your torso through the opening.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 36))
    draw.text((110, 610), "• Kick off the dashboard / door panel to push free.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 675), "• Do not try to bring bags, backpacks, or phones.", fill="#FCA5A5", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 740), "• Weight of wet clothes is heavy—stay streamlined.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    
    # Children reminder
    draw.rounded_rectangle([110, 810, WIDTH-110, 990], radius=16, fill=(8, 47, 73, 200), outline="#38BDF8", width=2)
    draw.text((140, 840), "PUSH KIDS OUT AHEAD OF YOU", fill="#F59E0B", font=get_font(FONT_BEBAS, 44))
    draw.text((140, 900), "Guide children up to the roof of the car first.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))

    # Swim to surface
    draw.rounded_rectangle([70, 1100, WIDTH-70, 1680], radius=24, fill=(15, 23, 42, 240), outline="#10B981", width=3)
    draw.text((110, 1140), "ONCE OUTSIDE THE VEHICLE:", fill="#10B981", font=get_font(FONT_BEBAS, 54))
    draw.text((110, 1220), "• If car is floating: climb onto the roof.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1280), "• If car is sinking: swim immediately towards light.", fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1340), "• Follow air bubbles if disoriented underwater.", fill="#38BDF8", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1400), "• Air bubbles ALWAYS travel straight up to surface.", fill="#6EE7B7", font=get_font(FONT_TIKTOK, 34))

    path = os.path.join(ASSETS_DIR, "visual_step3_escape.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 10: NEVER WAIT FOR WATER MYTH (13)
# ==============================================================================
def make_card_never_wait():
    im, draw = create_base_canvas(accent="#EF4444")
    draw_header(draw, "THE DEADLY MYTH", "WHY WAITING TO EQUALIZE WILL DROWN YOU", "MYTH BUSTED", "#EF4444")
    
    draw.rounded_rectangle([70, 360, WIDTH-70, 950], radius=24, fill=(35, 15, 20, 240), outline="#EF4444", width=3)
    
    draw.text((110, 400), "MYTH: 'WAIT UNTIL CAR FILLS WITH WATER'", fill="#FCA5A5", font=get_font(FONT_BEBAS, 50))
    draw.text((110, 470), "OLD ADVICE CLAIMED:", fill="#94A3B8", font=get_font(FONT_BEBAS, 38))
    draw.text((110, 520), "\"Wait for pressure to equalize, then push door.\"", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 32))
    
    draw.line([(110, 580), (WIDTH-110, 580)], fill=(75, 25, 30), width=2)
    
    draw.text((110, 610), "REALITY: 80%+ OF THOSE WHO WAIT DROWN", fill="#EF4444", font=get_font(FONT_BEBAS, 52))
    draw.text((110, 680), "• Pitch-black turbid water causes extreme disorientation.", fill="#FEE2E2", font=get_font(FONT_TIKTOK, 32))
    draw.text((110, 735), "• Car flips upside down in 70% of deep submersions.", fill="#FEE2E2", font=get_font(FONT_TIKTOK, 32))
    draw.text((110, 790), "• Finding door handle blind in freezing water is nearly impossible.", fill="#FEE2E2", font=get_font(FONT_TIKTOK, 32))
    
    # Verdict
    draw.rounded_rectangle([70, 1000, WIDTH-70, 1680], radius=24, fill=(15, 23, 42, 240), outline="#F59E0B", width=3)
    draw.text((110, 1050), "THE SURVIVAL LAW:", fill="#F59E0B", font=get_font(FONT_BEBAS, 60))
    draw.text((110, 1140), "ESCAPE WHILE THE CAR IS STILL FLOATING", fill="#FFFFFF", font=get_font(FONT_BEBAS, 52))
    draw.text((110, 1220), "• Cars float for 30 to 120 seconds before sinking.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1280), "• This is your ONLY golden window.", fill="#38BDF8", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1340), "• ACT IMMEDIATELY. Every second wasted is deadly.", fill="#EF4444", font=get_font(FONT_TIKTOK, 34))

    path = os.path.join(ASSETS_DIR, "visual_never_wait_water.png")
    im.save(path)
    print("Saved:", path)

# ==============================================================================
# CARD 11: FINAL RECAP & CTA (14)
# ==============================================================================
def make_card_final_recap():
    im, draw = create_base_canvas(accent="#10B981")
    draw_header(draw, "MEMORIZE S - W - O", "THE THREE LETTERS THAT SAVE LIVES", "SUMMARY", "#10B981")
    
    draw.rounded_rectangle([70, 360, WIDTH-70, 1240], radius=24, fill=(15, 26, 42, 240), outline="#10B981", width=4)
    
    # 3 big check items
    items = [
        ("01", "SEATBELT", "UNBUCKLE SELF & KIDS IMMEDIATELY", "#EF4444"),
        ("02", "WINDOW", "OPEN OR BREAK CORNER OF SIDE GLASS", "#F59E0B"),
        ("03", "OUT", "CLIMB OUT HEAD-FIRST BEFORE SINKING", "#10B981")
    ]
    for i, (num, title, sub, col) in enumerate(items):
        iy = 410 + i * 260
        draw.rounded_rectangle([100, iy, 200, iy+95], radius=14, fill=col)
        draw.text((120, iy+15), num, fill="#FFFFFF", font=get_font(FONT_BEBAS, 60))
        draw.text((225, iy+15), title, fill=col, font=get_font(FONT_BEBAS, 64))
        draw.text((110, iy+120), sub, fill="#FFFFFF", font=get_font(FONT_TIKTOK, 34))
        if i < 2:
            draw.line([(100, iy+210), (WIDTH-100, iy+210)], fill=(35, 45, 70), width=2)
            
    # Bottom Outro Box
    draw.rounded_rectangle([70, 1300, WIDTH-70, 1680], radius=24, fill=(30, 41, 59, 230), outline="#38BDF8", width=3)
    draw.text((110, 1340), "SHARE THIS WITH SOMEONE YOU CARE ABOUT", fill="#38BDF8", font=get_font(FONT_BEBAS, 50))
    draw.text((110, 1420), "Most drivers believe false myths about sinking cars.", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1475), "Knowing S-W-O beforehand is the difference", fill="#CBD5E1", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1530), "between life and death in an emergency.", fill="#F8FAFC", font=get_font(FONT_TIKTOK, 34))
    draw.text((110, 1600), "KINETIC CUT SURVIVAL SERIES", fill="#10B981", font=get_font(FONT_BEBAS, 36))

    path = os.path.join(ASSETS_DIR, "visual_final_swo_summary.png")
    im.save(path)
    print("Saved:", path)

# Run all card generators
make_card_water_pressure()
make_card_swo()
make_card_seatbelt()
make_card_children()
make_card_window()
make_card_windshield()
make_card_headrest()
make_card_corner()
make_card_escape()
make_card_never_wait()
make_card_final_recap()
print("All 11 visual cards generated successfully!")
