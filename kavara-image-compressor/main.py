from PIL import Image
import os
from typing import Tuple, Optional


SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def is_supported_image(filename: str) -> bool:
    """Check if file has supported image extension."""
    return filename.lower().endswith(SUPPORTED_EXTENSIONS)


def ensure_directory_exists(directory: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(directory, exist_ok=True)


def get_safe_output_path(input_path: str, output_dir: str, abs_output: str) -> Optional[str]:
    """Generate safe output path with .webp extension and path traversal protection."""
    filename = os.path.basename(input_path)
    base_name = os.path.splitext(filename)[0]
    output_path = os.path.abspath(os.path.join(output_dir, base_name + ".webp"))
    
    # Prevent path traversal attacks
    if os.path.commonpath([abs_output, output_path]) != abs_output:
        print(f"Skipping {filename}: Invalid output path")
        return None
    return output_path


def resize_image_if_needed(img: Image.Image, max_width: int, max_height: int) -> Image.Image:
    """Resize image if it exceeds maximum dimensions."""
    if img.width > max_width or img.height > max_height:
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return img


def convert_image_mode(img: Image.Image) -> Image.Image:
    """Convert RGBA and palette images to RGB."""
    if img.mode in ("RGBA", "P"):
        return img.convert("RGB")
    return img


def process_single_image(input_path: str, output_path: str, quality: int, 
                        max_width: int, max_height: int) -> Optional[Tuple[int, int, int, int]]:
    """Process a single image file. Returns (orig_w, orig_h, new_w, new_h) or None."""
    try:
        with Image.open(input_path) as img:
            original_size = img.size
            img = resize_image_if_needed(img, max_width, max_height)
            img = convert_image_mode(img)
            img.save(output_path, format="WEBP", quality=quality, method=3)
            return (*original_size, *img.size)
    except Exception as e:
        print(f"Error converting {os.path.basename(input_path)}: {e}")
        return None


def get_relative_display_path(rel_path: str) -> str:
    """Format relative path for display."""
    return f"{rel_path}/" if rel_path != "." else ""


def convert_to_webp(input_folder: str, output_folder: str, quality: int = 70, 
                   max_width: int = 1280, max_height: int = 853) -> None:
    """Convert and compress all images recursively with security protections."""
    abs_input = os.path.abspath(input_folder)
    abs_output = os.path.abspath(output_folder)
    
    for root, _, files in os.walk(abs_input):
        rel_path = os.path.relpath(root, abs_input)
        current_output = abs_output if rel_path == "." else os.path.join(abs_output, rel_path)
        ensure_directory_exists(current_output)
        
        for filename in files:
            if is_supported_image(filename):
                input_path = os.path.join(root, filename)
                output_path = get_safe_output_path(input_path, current_output, abs_output)
                
                if output_path:
                    result = process_single_image(input_path, output_path, quality, max_width, max_height)
                    if result:
                        orig_w, orig_h, new_w, new_h = result
                        resize_info = f" (resized from {orig_w}x{orig_h} to {new_w}x{new_h})" if (orig_w, orig_h) != (new_w, new_h) else ""
                        rel_display = get_relative_display_path(rel_path)
                        base_name = os.path.splitext(filename)[0]
                        print(f"Converted: {rel_display}{filename} → {base_name}.webp{resize_info}")

    print("✔ Conversion complete!")


def main() -> None:
    """Main function with configuration."""
    input_folder = "original_images"
    output_folder = "processed_images"
    quality = 55
    
    convert_to_webp(input_folder, output_folder, quality)


if __name__ == "__main__":
    main()
