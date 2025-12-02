# Kavara Background Remover

A simple command-line tool to remove backgrounds from images using `rembg`.

## Installation

1.  Navigate to the directory:
    ```bash
    cd kavara-bg-remover
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the script with an input image path. The output will be saved as a PNG file with the same name (appended with `_no_bg`) unless specified otherwise.

```bash
python main.py path/to/image.jpg
```

### Options

-   `-o`, `--output`: Specify the output file path.

```bash
python main.py input.jpg -o output.png
```
