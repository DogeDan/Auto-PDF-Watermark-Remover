#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF watermark removal tool - 3-step pipeline: extract -> process -> rebuild
"""

import cv2
import numpy as np
import fitz  # PyMuPDF
from pathlib import Path
from PIL import Image
import argparse
import sys
import shutil
import tempfile


def extract_pdf_to_images(pdf_path, output_folder, dpi=300, debug=False):
    """
    Step 1: Render all PDF pages to images and optionally save to a folder.

    Args:
        pdf_path: Path to the PDF file.
        output_folder: Folder to save extracted images (used in debug mode).
        dpi: Render resolution (default 300).
        debug: If True, save per-page PNG files and print progress.

    Returns:
        A list of numpy image arrays (debug=False) or list of saved image Paths (debug=True).
    """
    # Open PDF with basic error handling
    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error: Unable to open PDF file: {e}")
        sys.exit(1)
    
    total_pages = len(pdf_document)

    if debug:
        output_path = Path(output_folder)
        if output_path.exists():
            shutil.rmtree(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*50}")
        print(f"Step 1: Render PDF to images")
        print(f"{'='*50}")
        print(f"PDF: {Path(pdf_path).name}")
        print(f"Pages: {total_pages}")
        print(f"Output folder: {output_path.absolute()}\n")

    image_data = []

    for page_num in range(total_pages):
        if debug:
            print(f"Exporting page {page_num + 1}/{total_pages}...", end=" ")

        try:
            page = pdf_document[page_num]

            # Render the page at the given DPI (with fallback attempts)
            mat = fitz.Matrix(dpi/72, dpi/72)
            
            # Try rendering; if it fails, fall back to weaker options
            try:
                pix = page.get_pixmap(matrix=mat, alpha=False)
            except Exception as render_error:
                if debug:
                    print(f"\nWarning: error rendering page {page_num + 1}, attempting fallback: {render_error}")
                # 降级方案：使用更低的DPI或不同的渲染选项
                try:
                    pix = page.get_pixmap(matrix=mat, alpha=False, annots=False)
                except Exception:
                    # 最后的尝试：使用默认设置
                    pix = page.get_pixmap(alpha=False)

            # Convert pixmap bytes to a numpy image array
            img_data = pix.tobytes("ppm")
            img_array = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_UNCHANGED)

            if img_array is None:
                # Fallback: convert via PIL if direct decoding failed
                img_pil = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img_array = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

            if debug:
                # 保存为PNG
                output_file = output_path / f"page_{page_num + 1:03d}.png"
                cv2.imwrite(str(output_file), img_array)
                image_data.append(output_file)
                print(f"✓ Saved ({img_array.shape[1]}x{img_array.shape[0]}px)")
            else:
                # 直接存储图像数组
                image_data.append(img_array)

        except Exception as e:
            error_msg = f"Error: failed to process page {page_num + 1}: {e}"
            if debug:
                print(f"\n{error_msg}")
            else:
                print(error_msg)
            # Append a blank placeholder page if extraction fails
            blank_img = np.ones((int(11*dpi), int(8.5*dpi), 3), dtype=np.uint8) * 255
            image_data.append(blank_img)
            continue

    pdf_document.close()

    if debug:
        print(f"\n✓ All pages exported to: {output_path.absolute()}")
    
    return image_data


def remove_watermark_from_image(image_input, output_path=None):
    """
    Step 2: Remove watermark from a single image.

    Args:
        image_input: Path to an image file or a numpy image array.
        output_path: If provided, save the processed image to this path.

    Returns:
        The processed image as a numpy array (and saves to output_path when given).
    """
    # Read input image (from path or use the provided array)
    if isinstance(image_input, (str, Path)):
        img = cv2.imread(str(image_input))
    else:
        img = image_input.copy()
    
    original_img = img.copy()

    # Auto-detect watermark color using a coarse 3D color histogram
    hist = cv2.calcHist([img], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()

    # Find the most frequent colors in the histogram
    sorted_indices = np.argsort(hist)[::-1]

    watermark_color_rgb = None
    for idx in sorted_indices:
        # Convert histogram bin index to (r,g,b) bin and compute center value
        r_bin, g_bin, b_bin = np.unravel_index(idx, (8, 8, 8))
        r = r_bin * 32 + 16
        g = g_bin * 32 + 16
        b = b_bin * 32 + 16

        # Skip very dark colors (likely text) and near-gray colors (likely background)
        if (r + g + b) < 150:
            continue
        color_diff = max(r, g, b) - min(r, g, b)
        if color_diff < 20:
            continue

        watermark_color_rgb = (r, g, b)
        break

    # Fallback default color if auto-detection fails
    if watermark_color_rgb is None:
        watermark_color_rgb = (230, 230, 230)


    # Build a BGR range mask around the detected color (per-channel tolerance)
    tol = 80  # per-channel tolerance
    r, g, b = watermark_color_rgb
    target_bgr = np.array([b, g, r], dtype=np.int16)

    # Create an initial color range
    lower_bgr = np.clip(target_bgr - tol, 0, 255).astype(np.uint8)
    upper_bgr = np.clip(target_bgr + tol, 0, 255).astype(np.uint8)

    # Create a mask where pixels fall within the BGR ranges
    mask = cv2.inRange(img, lower_bgr, upper_bgr)

    # Expand mask by testing several tolerance multipliers
    for i in range(1, 4):  # try multiple tolerance multipliers
        lower_bgr = np.clip(target_bgr - tol * i, 0, 255).astype(np.uint8)
        upper_bgr = np.clip(target_bgr + tol * i, 0, 255).astype(np.uint8)
        mask += cv2.inRange(img, lower_bgr, upper_bgr)

    # Morphological operations to clean up the mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=5)

    if np.sum(mask) == 0:
        # No watermark pixels detected — return original image
        if output_path:
            cv2.imwrite(str(output_path), original_img)
        return original_img

    # Convert to HSV for saturation/value based adjustments
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Reduce saturation in masked areas to desaturate the watermark
    hsv_adjusted = hsv.copy()
    hsv_adjusted[mask > 0, 1] = 0

    # Convert desaturated result back to BGR; prepare refinement masks
    result = cv2.cvtColor(hsv_adjusted, cv2.COLOR_HSV2BGR)

    sat_channel = hsv_adjusted[:, :, 1]
    val_channel = hsv_adjusted[:, :, 2]

    refined_mask = mask.copy()
    refined_mask[sat_channel > 30] = 0
    refined_mask[val_channel < 175] = 0

    text_mask = cv2.bitwise_and(mask, cv2.bitwise_not(refined_mask))
    # Preserve text-like regions by copying from original image
    result[text_mask > 0] = original_img[text_mask > 0]
    
    
    # # Example alternative approach (commented out):
    # # y_coords, x_coords = np.where(refined_mask > 0)
    # # for y, x in zip(y_coords, x_coords):
    # #     r, g, b = original_img[y, x]
    # #     color_diff = max(r, g, b) - min(r, g, b)
    # #     if color_diff < 20:
    # #         continue
    # #     result[y, x] = [255, 255, 255]
    
    # Within refined_mask, detect pixels with sufficient channel variation
    pixels = original_img[refined_mask > 0]
    color_diffs = np.max(pixels, axis=1) - np.min(pixels, axis=1)
    keep_mask = color_diffs >= 50
    y_coords, x_coords = np.where(refined_mask > 0)
    # Replace selected pixels with white (targeting gray watermark regions)
    for i, should_modify in enumerate(keep_mask):
        if should_modify:
            y, x = y_coords[i], x_coords[i]
            result[y, x] = [255, 255, 255]
    
    # result[refined_mask > 0] = [255, 255, 255]

    # Save processed image if requested
    if output_path:
        cv2.imwrite(str(output_path), result)

    return result


def process_images_in_folder(input_data, output_folder, debug=False):
    """
    Step 2 (full): Process all images in a folder

    Args:
        input_data: Path to a folder containing original images or a list of image arrays
        output_folder: Folder to save processed images (used in debug mode)
        debug: Whether to print detailed progress and save intermediate files
    Returns:
        List of processed image arrays (debug=False) or list of saved Paths (debug=True)
    """
    if debug:
        input_path = Path(input_data)
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*50}")
        print(f"Step 2: Process all images (remove watermark)")
        print(f"{'='*50}")
        print(f"Input folder: {input_path.absolute()}")
        print(f"Output folder: {output_path.absolute()}")

        # 获取所有PNG文件
        image_files = sorted(input_path.glob("page_*.png"))
        total_images = len(image_files)

        if total_images == 0:
            print("Error: No image files found")
            return []

        processed_paths = []

        for idx, image_file in enumerate(image_files, 1):
            print(f"Processing image {idx}/{total_images}: {image_file.name}...", end=" ")
            output_file = output_path / image_file.name
            processed_img = remove_watermark_from_image(image_file, output_file)
            processed_paths.append(output_file)
            print("✓")

        print(f"\n✓ All images processed")
        return processed_paths
    else:
        # Non-debug mode: process images in memory
        processed_images = []
        for img_array in input_data:
            processed_img = remove_watermark_from_image(img_array)
            processed_images.append(processed_img)
        return processed_images


def rebuild_pdf_from_images(image_data, output_pdf_path, debug=False):
    """
    Step 3: Rebuild PDF from processed images

    Args:
        image_data: Path to folder with processed images or a list of image arrays
        output_pdf_path: Output PDF file path
        debug: Whether to print detailed progress
    """
    if debug:
        image_path = Path(image_data)
        print(f"\n{'='*50}")
        print(f"Step 3: Rebuild PDF from images")
        print(f"{'='*50}")
        print(f"Input folder: {image_path.absolute()}")
        print(f"Output PDF: {output_pdf_path}\n")

        # 获取所有PNG文件，按顺序排序
        image_files = sorted(image_path.glob("page_*.png"))

        if not image_files:
            print("Error: No image files found")
            return False

        print(f"Found {len(image_files)} images")
        print("Loading images...", end=" ")

        pil_images = []
        for image_file in image_files:
            img = Image.open(image_file)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            pil_images.append(img)

        print(f"✓\nSaving PDF...", end=" ")
    else:
        # 非debug模式：直接从numpy数组转换
        pil_images = []
        for img_array in image_data:
            # OpenCV uses BGR, PIL uses RGB
            img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            pil_images.append(pil_img)

    # 保存为PDF
    pil_images[0].save(
        output_pdf_path,
        save_all=True,
        append_images=pil_images[1:] if len(pil_images) > 1 else [],
        duration=0,
        loop=0
    )

    if debug:
        print(f"✓\n✓ PDF rebuild complete: {output_pdf_path}")
    
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="PDF watermark removal tool - batch mode (three-step pipeline)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  python watermarkrm.py -r 249 -g 249 -b 249
  python watermarkrm.py -r 249 -g 249 -b 249 --debug

  Where RGB(249, 249, 249) is the detected watermark color.
  Use --debug to enable verbose output and save intermediate files.

All PDF files in the current directory will be processed and output to ./output/
        """
    )

    # parser.add_argument("-r", "--red", type=int, required=True, help="Watermark red component (0-255)")
    # parser.add_argument("-g", "--green", type=int, required=True, help="Watermark green component (0-255)")
    # parser.add_argument("-b", "--blue", type=int, required=True, help="Watermark blue component (0-255)")
    parser.add_argument("--debug", action="store_true", help="Enable verbose output and save intermediate files")

    args = parser.parse_args()

    if args.debug:
        print("=" * 50)
        print("   PDF Watermark Removal Tool (batch mode)")
        print("=" * 50)

    # 验证颜色
    # if not all(0 <= val <= 255 for val in [args.red, args.green, args.blue]):
    #     print("错误：颜色值必须在 0-255 之间")
    #     sys.exit(1)

    # 查找当前目录下所有PDF文件
    current_dir = Path(".")
    pdf_files = sorted(current_dir.glob("*.pdf"))

    if not pdf_files:
        print("Error: No PDF files found in the current directory")
        sys.exit(1)

    # 创建output文件夹
    output_dir = current_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # 定义中间文件夹（仅debug模式使用）
    # Define intermediate folders (used in debug mode)
    images_extracted_folder = "images_extracted"
    images_cleaned_folder = "images_cleaned"

    for pdf_file in pdf_files:
        print(f"\n{'='*50}")
        print(f"Processing file: {pdf_file.name}")
        print(f"{'='*50}")

        output_pdf = output_dir / pdf_file.name

        try:
            if args.debug:
                # Debug mode: save intermediate files
                # Step 1: Render PDF pages to images
                image_paths = extract_pdf_to_images(pdf_file, images_extracted_folder, debug=True)

                # Step 2: Process all images
                processed_paths = process_images_in_folder(images_extracted_folder, images_cleaned_folder, debug=True)

                # Step 3: Rebuild PDF from processed images
                success = rebuild_pdf_from_images(images_cleaned_folder, output_pdf, debug=True)
            else:
                # Non-debug mode: in-memory processing, no intermediate files
                # Step 1: Render PDF pages to image arrays
                image_arrays = extract_pdf_to_images(pdf_file, None, debug=False)

                # Step 2: Process all images
                processed_arrays = process_images_in_folder(image_arrays, None, debug=False)

                # Step 3: Rebuild PDF from processed images
                success = rebuild_pdf_from_images(processed_arrays, output_pdf, debug=False)

            if success:
                print(f"\n✓ Done!")
                print(f"Output file: {output_pdf}")
                if args.debug:
                    print(f"Intermediate folders:")
                    print(f"  - Extracted images: ./{images_extracted_folder}/")
                    print(f"  - Cleaned images: ./{images_cleaned_folder}/")
                    print(f"Intermediate folders:")
                    print(f"  - Extracted images: ./{images_extracted_folder}/")
                    print(f"  - Cleaned images: ./{images_cleaned_folder}/")

        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            continue

if __name__ == "__main__":
    main()
