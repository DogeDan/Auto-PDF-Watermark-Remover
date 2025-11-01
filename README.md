# Auto PDF Watermark Remover
[中文](readme-zh.md)｜[English](README.md)

## Example

Below is a comparison of a sample page before and after watermark removal.  
Left: original image (`input-samples`), right: processed image (`output-samples`).

| Original | Cleaned |
|:--------:|:-------:|
| <img src="input-samples/sample(rotatetext)_page_1.png" width="320"/> | <img src="output-samples/sample(rotatetext)_page_1.png" width="320"/> |
| <img src="input-samples/sample(Leftlogo)_page_1.png" width="320"/> | <img src="output-samples/sample(Leftlogo)_page_1.png" width="320"/> |
| <img src="input-samples/sample(Draft)_page_1.png" width="320"/> | <img src="output-samples/sample(Draft)_page_1.png" width="320"/> |
| <img src="input-samples/sample(Secrect)_page_1.png" width="320"/> | <img src="output-samples/sample(Secrect)_page_1.png" width="320"/> |

<!-- You can add more samples as needed:
| <img src="input-samples/sample2.png" width="320"/> | <img src="output-samples/sample2.png" width="320"/> |
-->

A small, local Python toolkit that attempts to remove or reduce visible colored watermarks from PDF files by rendering pages to images, processing the images to remove watermark regions, and rebuilding the PDF. It provides two scripts:

- `watermarkrm-rgb.py` — user-specified watermark color (RGB) processing.
- `watermarkrm-auto.py` — attempts to auto-detect a likely watermark color and process pages automatically.

Both scripts operate in a three-step pipeline: extract PDF pages to images, remove watermark pixels on each image, then rebuild a new PDF from the cleaned images.

**Important:** This toolkit targets colored watermarks only. Black-and-white (grayscale) or pure black text-like watermarks are not supported and typically require other techniques (e.g., content-level/vector removal, binarization/threshold cleanup).

## Features

- Processes all `*.pdf` files in the current working directory.
- Two modes: manual RGB color mode (precise) and auto-detect mode (convenient).
- Debug mode saves intermediate images so you can inspect extracted/cleaned pages.
- Purely local — no network calls; uses OpenCV and PyMuPDF (fitz).

## How it works (high level)

1. Render each PDF page to an image using PyMuPDF at a configurable DPI.
2. Detect watermark pixels (either from a user-provided RGB center value or by auto-detection) and build color masks.
3. Apply morphological operations and HSV-based adjustments to reduce watermark visibility, replacing/removing watermark pixels where appropriate.
4. Rebuild a new PDF from cleaned images.

Note: This tool attempts a best-effort removal of simple colored/transparent watermarks. Complex, blended, or vector watermarks may not be fully removed.

## Requirements

- Python 3.8 or newer
- Packages (install with pip):
  - PyMuPDF (imported as `fitz`)
  - opencv-python (cv2)
  - numpy
  - Pillow

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install pymupdf opencv-python numpy pillow
```

## Usage

1. Put the PDF files you want to process into the same folder as the scripts (or cd to that folder).
2. Run one of the scripts below.

### Manual RGB mode (precise)

Use `watermarkrm-rgb.py` when you know the approximate color of the watermark.

```bash
python watermarkrm-rgb.py -r <RED> -g <GREEN> -b <BLUE>

# Example:
python watermarkrm-rgb.py -r 249 -g 249 -b 249
```

Options:
- `-r`, `--red` — red channel 0–255 (required)
- `-g`, `--green` — green channel 0–255 (required)
- `-b`, `--blue` — blue channel 0–255 (required)
- `--debug` — enable debug mode and save intermediate images

### Auto-detect mode (convenient)

Use `watermarkrm-auto.py` when you don't know the watermark color. The script will try to detect a likely watermark color automatically.

```bash
python watermarkrm-auto.py

# With debug (saves intermediate images):
python watermarkrm-auto.py --debug
```

### What happens in debug mode

When `--debug` is passed, the scripts will create two folders in the current directory for each processed PDF:

- `images_extracted/` — rendered page PNGs
- `images_cleaned/` — processed PNGs after watermark removal

The final cleaned PDFs are written to `./output/` with the original filenames.

## Tips & tuning

- DPI: scripts default to rendering pages at 300 DPI. Increasing DPI improves image fidelity but uses more memory and disk.
- If auto mode fails to remove the watermark cleanly, try `watermarkrm-rgb.py` with the detected color (you can inspect `images_extracted/` to sample pixels).
- For faint/complex watermarks, manual tuning of the color tolerance and morphological parameters in the scripts may help (see the variables `tol`, kernel sizes, and dilation iterations).

## Limitations

- Does not support black-and-white/grayscale watermarks; use other approaches (e.g., content-level editing, binarization/threshold tools).
- This tool is best for simple colored or semi-transparent watermarks. It may not work well for:
  - Vector watermarks embedded in the PDF content stream
  - Watermarks blended with background textures or gradients
  - Documents with complex layered transparency

Use this tool as a convenience for quick local cleanups. Always keep backups of originals.

## Troubleshooting

- Error opening PDF: ensure the file is not password-protected and is a valid PDF.
- If you see blank or corrupted output pages, try lowering DPI or running with `--debug` to inspect the extracted PNGs.
- If dependencies fail to import, re-run the pip install commands above.

## License & credits

- License: MIT. See the LICENSE file for full terms.
- You may use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies under the MIT license; retain copyright and license notices.
- Credits: Thanks to the authors and maintainers of PyMuPDF (fitz), OpenCV, NumPy, and Pillow.

## Contact

If you need help or want to contribute, open an issue or create a PR in this repository.
