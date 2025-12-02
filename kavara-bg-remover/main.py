import argparse
import os
from rembg import remove
from PIL import Image
import io

def remove_background(input_path, output_path=None):
    """
    Removes the background from an image.

    Args:
        input_path (str): Path to the input image.
        output_path (str, optional): Path to save the output image. 
                                     If None, defaults to input filename + '_no_bg.png'.
    """
    try:
        # Validate input
        if not os.path.exists(input_path):
            print(f"Error: Input file '{input_path}' not found.")
            return

        # Determine output path if not provided
        if not output_path:
            base, _ = os.path.splitext(input_path)
            output_path = f"{base}_no_bg.png"

        print(f"Processing: {input_path}...")

        # Open the image
        with open(input_path, 'rb') as i:
            input_data = i.read()
            
        # Remove background
        output_data = remove(input_data)

        # Save the result
        with open(output_path, 'wb') as o:
            o.write(output_data)

        print(f"Success! Background removed. Saved to: {output_path}")

    except Exception as e:
        print(f"An error occurred: {e}")

def main():
    parser = argparse.ArgumentParser(description="Remove background from an image.")
    parser.add_argument("input", help="Path to the input image file.")
    parser.add_argument("-o", "--output", help="Path to the output PNG file.")

    args = parser.parse_args()

    remove_background(args.input, args.output)

if __name__ == "__main__":
    main()
