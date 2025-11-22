# 🖼️ Kavara Image Compressor

A Python utility for batch converting and compressing images to WebP format with optimized compression settings.

## 📋 Overview

This tool converts images from common formats (JPG, JPEG, PNG, WebP) to WebP format with configurable quality settings. It's designed for bulk image processing to reduce file sizes while maintaining acceptable image quality.

## ✨ Features

- **📁 Batch Processing**: Convert entire folders of images at once
- **🔄 Multiple Format Support**: Handles JPG, JPEG, PNG, and WebP input formats
- **🎛️ Quality Control**: Configurable compression quality (1-100)
- **📂 Automatic Directory Creation**: Creates output directories if they don't exist
- **🎨 Color Mode Handling**: Automatically converts RGBA and palette images to RGB
- **🛡️ Error Handling**: Continues processing even if individual files fail
- **📊 Progress Feedback**: Real-time conversion status updates

## 📋 Requirements

- 🐍 Python 3.6+
- 🖼️ Pillow (PIL) library

## 🚀 Installation

1. Clone or download this repository
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 💻 Usage

### 🔧 Basic Usage

```python
from main import convert_to_webp

# Convert images with default settings
convert_to_webp("original_images", "processed_images", quality=70)
```

### ⚙️ Configuration Options

```python
# High quality conversion (larger files)
convert_to_webp("input_folder", "output_folder", quality=90)

# Maximum compression (smaller files, lower quality)
convert_to_webp("input_folder", "output_folder", quality=30)

# Balanced compression (recommended)
convert_to_webp("input_folder", "output_folder", quality=55)
```

### ▶️ Running the Script

1. Place your images in the `original_images` folder
2. Modify the configuration in `main.py` if needed:
   ```python
   input_folder = "original_images"
   output_folder = "processed_images"
   quality = 55  # Adjust between 1-100
   ```
3. Run the script:
   ```bash
   python main.py
   ```

## 📚 Function Reference

### `convert_to_webp(input_folder, output_folder, quality=70)`

Converts and compresses all supported images in a folder to WebP format.

**📝 Parameters:**

- `input_folder` (str): Path to folder containing original images
- `output_folder` (str): Path where WebP images will be saved
- `quality` (int, optional): WebP quality setting (1-100, default: 70)

**📁 Supported Input Formats:**

- `.jpg`, `.jpeg`
- `.png`
- `.webp`

**⭐ Features:**

- Creates output directory automatically
- Preserves original filenames (changes extension to .webp)
- Converts RGBA and palette images to RGB for compatibility
- Uses method=3 for best compression efficiency

## 📊 Quality Guidelines

| Quality Range | Use Case                              | File Size  | Image Quality |
| ------------- | ------------------------------------- | ---------- | ------------- |
| 80-100        | High-quality photos, professional use | Large      | Excellent     |
| 60-79         | General web use, good balance         | Medium     | Good          |
| 40-59         | Web optimization, faster loading      | Small      | Acceptable    |
| 1-39          | Maximum compression, thumbnails       | Very Small | Lower         |

## 📁 Project Structure

```
kavara-image-compressor/
├── main.py              # Main conversion script
├── README.md            # This documentation
├── requirements.txt     # Python dependencies
├── original_images/     # Input folder (your images go here)
└── processed_images/        # Output folder (converted images)
```

## 🛡️ Error Handling

The script includes robust error handling:

- ✅ Continues processing if individual files fail to convert
- ❌ Displays error messages for problematic files
- ✔️ Provides completion confirmation

## ⚡ Performance Notes

- 🖥️ WebP conversion is CPU-intensive for large images
- ⏱️ Processing time depends on image size and quality settings
- 🚀 Lower quality settings process faster
- 🔧 Method=3 provides best compression but takes longer

## 🔧 Troubleshooting

**❗ Common Issues:**

1. **"No module named 'PIL'"**

   - 💡 Install Pillow: `pip install Pillow`

2. **🔒 Permission errors**

   - 💡 Ensure write permissions for output directory
   - 💡 Run as administrator if necessary

3. **📄 Unsupported file format**

   - 💡 Check that input files have supported extensions
   - 💡 Verify files aren't corrupted

4. **💾 Memory errors with large images**
   - 💡 Process images in smaller batches
   - 💡 Reduce quality setting for very large files

## 📄 License

This project is open source. Feel free to modify and distribute as needed.

## 🤝 Contributing

1. 🍴 Fork the repository
2. 🌿 Create a feature branch
3. ✏️ Make your changes
4. 🧪 Test thoroughly
5. 📤 Submit a pull request

## 📝 Changelog

### 🎉 Version 1.0

- 🚀 Initial release
- 🖼️ Basic WebP conversion functionality
- 📁 Batch processing support
- 🎛️ Quality control options
