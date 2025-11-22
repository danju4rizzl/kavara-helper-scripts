# CSV Modification Script

This project contains a Python script (`main.py`) designed to clean and format product data CSV files for WooCommerce import. It automates several tasks such as fixing image URLs, formatting JSON swatches, setting brand names, and ensuring all required WooCommerce columns are present.

## Features

-   **Image URL Fixes**: Updates image paths to a target year/month and converts extensions to `.webp`.
-   **Swatches JSON Fix**: Renames the "color" key to "Colors" (or your configured attribute name) in JSON strings.
-   **Brand Assignment**: Sets a default brand for all products.
-   **WooCommerce Compatibility**: Ensures all standard WooCommerce import columns exist and are correctly ordered.
-   **Parent/Child Linking**: Fixes parent-child relationships for variable products.

## Prerequisites

-   Python 3.x installed on your system.

## Installation

1.  Clone or download this repository.
2.  Open a terminal/command prompt in the project directory.
3.  Install the required dependencies:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Prepare your data**:
    *   Place your raw export CSV file in the project directory.
    *   Rename it to `RAW-DATA.csv` (or update the `INPUT_FILE` variable in `main.py`).

2.  **Configure the script** (Optional):
    *   Open `main.py` in a text editor.
    *   Modify the `CONFIGURATION` section at the top to match your needs (e.g., `TARGET_YEAR_MONTH`, `BRAND_NAME`).

3.  **Run the script**:

    ```bash
    python main.py
    ```

4.  **Output**:
    *   The cleaned file will be saved as `clean.csv` (or your configured `OUTPUT_FILE`).
    *   This file is now ready to be imported into WooCommerce.
