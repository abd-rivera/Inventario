#!/usr/bin/env python3
"""Generate PWA icons"""
from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size):
    """Create a Plus Control icon of given size"""
    # Create image with blue background
    img = Image.new('RGB', (size, size), color='#3b82f6')
    draw = ImageDraw.Draw(img)
    
    # Draw white "PC" text
    # Using a simple approach with large font
    text = "PC"
    
    # Calculate text position to center it
    # For now, just draw a simple design
    margin = size // 8
    
    # Draw background circle
    draw.ellipse(
        [(margin, margin), (size - margin, size - margin)],
        fill='#1e40af',
        outline='#ffffff',
        width=2
    )
    
    # Try to add text (may not have fonts, so we'll draw simple shapes)
    try:
        # Try to use default font
        font = ImageFont.load_default()
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        x = (size - text_width) // 2
        y = (size - text_height) // 2
        
        draw.text((x, y), text, fill='white', font=font)
    except:
        # If fonts fail, just draw rectangles
        center = size // 2
        rect_size = size // 4
        draw.rectangle(
            [(center - rect_size, center - rect_size),
             (center + rect_size, center + rect_size)],
            fill='white'
        )
    
    return img

# Create icons
icon_192 = create_icon(192)
icon_512 = create_icon(512)

# Save in front directory
front_dir = os.path.dirname(os.path.abspath(__file__))
if front_dir.endswith('back'):
    front_dir = os.path.join(os.path.dirname(front_dir), 'front')

icon_192.save(os.path.join(front_dir, 'icon-192.png'))
icon_512.save(os.path.join(front_dir, 'icon-512.png'))

print("✓ Icons created: icon-192.png and icon-512.png")
