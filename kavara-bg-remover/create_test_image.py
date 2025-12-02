from PIL import Image, ImageDraw

def create_test_image(path):
    # Create a new image with a white background
    img = Image.new('RGB', (200, 200), color='white')
    d = ImageDraw.Draw(img)
    
    # Draw a red circle in the center
    d.ellipse((50, 50, 150, 150), fill='red')
    
    img.save(path)
    print(f"Test image saved to {path}")

if __name__ == "__main__":
    create_test_image("test_image.jpg")
