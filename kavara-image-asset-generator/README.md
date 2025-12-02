# Kavara Image Asset Generator

A Python script that generates multiple icon sizes from a single input image for various platforms including Favicon, Apple Touch Icons, Android Chrome, Microsoft Tiles, and PWA Manifest icons.

## Features

- ✨ Supports multiple input formats: PNG, JPEG, SVG, WebP, BMP, GIF
- 📱 Generates icons for all major platforms
- 🎯 Organized output with platform-specific subdirectories
- 🖼️ Optional aspect ratio preservation with transparent padding
- ⚡ High-quality image resizing using Lanczos resampling
- 📊 Progress feedback during generation

## Generated Icon Sizes

### Favicon
- 16x16 px
- 32x32 px
- 48x48 px

### Apple Touch Icon
- 120x120 px (iPhone Retina)
- 152x152 px (iPad Retina)
- 180x180 px (iPhone Retina iOS 11+)

### Android Chrome Icons
- 192x192 px (recommended for PWA)
- 512x512 px (Google Play store icon)

### Microsoft Tiles
- 70x70 px (small tile)
- 150x150 px (medium tile)
- 310x150 px (wide tile)
- 310x310 px (large tile)

### PWA Manifest Icons
- 48x48 px
- 72x72 px
- 96x96 px
- 144x144 px
- 192x192 px
- 256x256 px
- 384x384 px
- 512x512 px

## Installation

1. **Clone or navigate to the directory:**
   ```bash
   cd kavara-image-asset-generator
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Basic Usage

Generate icons from an input image:

```bash
python main.py logo.png
```

This will create an `output` directory with subdirectories for each platform containing all the generated icons.

### Custom Output Directory

Specify a custom output directory:

```bash
python main.py logo.png -o my-icons
```

### Maintain Aspect Ratio

Preserve the original aspect ratio and pad with transparency:

```bash
python main.py logo.png --maintain-aspect
```

### Full Example

```bash
python main.py assets/logo.svg -o dist/icons --maintain-aspect
```

## Output Structure

After running the script, your output directory will have the following structure:

```
output/
├── favicon/
│   ├── icon-16x16.png
│   ├── icon-32x32.png
│   └── icon-48x48.png
├── apple-touch/
│   ├── icon-120x120.png
│   ├── icon-152x152.png
│   └── icon-180x180.png
├── android-chrome/
│   ├── icon-192x192.png
│   └── icon-512x512.png
├── microsoft-tiles/
│   ├── icon-70x70.png
│   ├── icon-150x150.png
│   ├── icon-310x150.png
│   └── icon-310x310.png
└── pwa-manifest/
    ├── icon-48x48.png
    ├── icon-72x72.png
    ├── icon-96x96.png
    ├── icon-144x144.png
    ├── icon-192x192.png
    ├── icon-256x256.png
    ├── icon-384x384.png
    └── icon-512x512.png
```

## Command-Line Options

```
usage: main.py [-h] [-o OUTPUT] [--maintain-aspect] input

positional arguments:
  input                 Input image file (png, jpeg, svg, webp, etc.)

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output directory (default: output)
  --maintain-aspect     Maintain aspect ratio and pad with transparency
```

## Requirements

- Python 3.7+
- Pillow (PIL) library

## Tips

- **Best Input Image**: Use a high-resolution square image (at least 512x512 px) for best results
- **Transparent Background**: PNG files with transparent backgrounds work best
- **SVG Support**: SVG files are supported but require the image to be rasterized first
- **Aspect Ratio**: Use `--maintain-aspect` flag if your logo is not square to avoid distortion

## License

MIT License - Feel free to use this script in your projects!

## Author

Created for the Kavara Helper Scripts collection.
