#!/usr/bin/env python3
"""Generate placeholder icons for MyBlink PWA."""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size, filename):
    """Create a simple camera icon."""
    # Create image with blue background
    img = Image.new('RGB', (size, size), color='#2563eb')
    draw = ImageDraw.Draw(img)
    
    # Draw camera shape (simplified)
    margin = size // 8
    cam_x1, cam_y1 = margin, margin * 2
    cam_x2, cam_y2 = size - margin, size - margin
    
    # Camera body
    draw.rectangle([cam_x1, cam_y1, cam_x2, cam_y2], fill='white', outline='white', width=2)
    
    # Lens
    center = size // 2
    radius = size // 4
    draw.ellipse([center - radius, center - radius, center + radius, center + radius], 
                 fill='#2563eb', outline='#1d4ed8', width=size//40)
    
    # Viewfinder
    vf_size = size // 10
    draw.rectangle([size - margin * 2, margin, size - margin, margin + vf_size], 
                   fill='#1d4ed8')
    
    # Save
    img.save(filename, 'PNG')
    print(f'Created {filename}')

# Create icons
create_icon(192, 'icon-192.png')
create_icon(512, 'icon-512.png')

print('Icons created successfully!')
