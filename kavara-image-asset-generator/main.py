#!/usr/bin/env python3
"""
Kavara Image Asset Generator
Generates multiple icon sizes from a single input image for various platforms.
"""

import os
import sys
from pathlib import Path
from PIL import Image
import argparse


# Define icon sizes for different platforms
ICON_SIZES = {
    "favicon": [
        (16, 16),
        (32, 32),
        (48, 48),
    ],
    "apple-touch": [
        (120, 120),  # iPhone Retina
        (152, 152),  # iPad Retina
        (180, 180),  # iPhone Retina iOS 11+
    ],
    "android-chrome": [
        (192, 192),  # PWA recommended
        (512, 512),  # Google Play store icon
    ],
    "microsoft-tiles": [
        (70, 70),    # Small tile
        (150, 150),  # Medium tile
        (310, 150),  # Wide tile
        (310, 310),  # Large tile
    ],
    "pwa-manifest": [
        (48, 48),
        (72, 72),
        (96, 96),
        (144, 144),
        (192, 192),
        (256, 256),
        (384, 384),
        (512, 512),
    ],
}


def resize_image(input_path: str, output_path: str, size: tuple, maintain_aspect: bool = False):
    """
    Resize an image to the specified size.
    
    Args:
        input_path: Path to the input image
        output_path: Path to save the resized image
        size: Tuple of (width, height)
        maintain_aspect: If True, maintain aspect ratio and pad with transparency
    """
    try:
        with Image.open(input_path) as img:
            # Convert to RGBA to handle transparency
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            if maintain_aspect:
                # Calculate aspect ratio
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Create a new image with the target size and transparent background
                new_img = Image.new('RGBA', size, (0, 0, 0, 0))
                
                # Paste the resized image in the center
                paste_x = (size[0] - img.width) // 2
                paste_y = (size[1] - img.height) // 2
                new_img.paste(img, (paste_x, paste_y))
                img = new_img
            else:
                # Direct resize
                img = img.resize(size, Image.Resampling.LANCZOS)
            
            # Save the image
            img.save(output_path, 'PNG', optimize=True)
            print(f"✓ Created: {output_path} ({size[0]}x{size[1]})")
            
    except Exception as e:
        print(f"✗ Error creating {output_path}: {str(e)}")


def generate_icons(input_file: str, output_dir: str = "output", maintain_aspect: bool = False):
    """
    Generate all icon sizes from the input image.
    
    Args:
        input_file: Path to the input image file
        output_dir: Directory to save the generated icons
        maintain_aspect: If True, maintain aspect ratio and pad with transparency
    """
    # Validate input file
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found!")
        sys.exit(1)
    
    # Validate input file format
    valid_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.webp', '.bmp', '.gif']
    file_ext = Path(input_file).suffix.lower()
    if file_ext not in valid_extensions:
        print(f"Error: Unsupported file format '{file_ext}'")
        print(f"Supported formats: {', '.join(valid_extensions)}")
        sys.exit(1)
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    print(f"\n🎨 Generating icons from: {input_file}")
    print(f"📁 Output directory: {output_dir}\n")
    
    # Generate icons for each platform
    total_icons = 0
    for platform, sizes in ICON_SIZES.items():
        print(f"\n📱 {platform.upper().replace('-', ' ')}")
        print("=" * 50)
        
        # Create platform subdirectory
        platform_dir = output_path / platform
        platform_dir.mkdir(exist_ok=True)
        
        # Generate each size
        for size in sizes:
            width, height = size
            output_file = platform_dir / f"icon-{width}x{height}.png"
            resize_image(input_file, str(output_file), size, maintain_aspect)
            total_icons += 1
    
    print(f"\n✅ Successfully generated {total_icons} icons!")
    print(f"📂 All icons saved to: {output_dir}/")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Generate multiple icon sizes from a single input image.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py logo.png
  python main.py logo.svg -o icons
  python main.py logo.png -o my-icons --maintain-aspect
        """
    )
    
    parser.add_argument(
        'input',
        help='Input image file (png, jpeg, svg, webp, etc.)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='output',
        help='Output directory (default: output)'
    )
    
    parser.add_argument(
        '--maintain-aspect',
        action='store_true',
        help='Maintain aspect ratio and pad with transparency'
    )
    
    args = parser.parse_args()
    
    # Generate icons
    generate_icons(args.input, args.output, args.maintain_aspect)


if __name__ == "__main__":
    main()
