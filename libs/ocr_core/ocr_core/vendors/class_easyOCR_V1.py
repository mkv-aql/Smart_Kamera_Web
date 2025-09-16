__author__ = 'mkv-aql'

import ast
import easyocr
import cv2
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import random

# example of random integer values
# random.seed(0)
# for _ in range(10):
#     print(random.randint(0, 100))

# Set global Pandas and NumPy options
pd.set_option('display.max_columns', None)  # Display all columns
np.set_printoptions(linewidth=200, precision=4)


class OCRProcessor:
    def __init__(self, language='de', gpu=True, recog_network='latin_g2'):
        """
        Initialize the OCR processor.

        :param language: The language for the OCR model.
        :param gpu: Whether to use GPU for OCR processing.
        :param recog_network: The recognition network to use (default is 'latin_g2').
        """
        self.reader = easyocr.Reader([language], gpu=gpu, recog_network=recog_network)

    def ocr(self, image_path):
        """
        Perform OCR on the given image.

        :param image_path: Path to the image file.
        :return: A DataFrame containing OCR results (bbox, Namen, Confidence Level).
        """
        image = cv2.imread(image_path)
        ocr_results = self.reader.readtext(image, contrast_ths=0.05,
                                           adjust_contrast=0.7,
                                           text_threshold=0.8,
                                           low_text=0.4)
        df_ocr_results = pd.DataFrame(ocr_results,
                                      columns=['bbox', 'Namen', 'Confidence Level'])

        df_ocr_results.insert(3, 'Bildname', image_path.split('/')[-1].split('.')[0])

        return df_ocr_results

    def save_to_csv(self, df_ocr_results, image_path, save_path):
        """
        Convert all doubles to integers.
        Save the OCR results DataFrame to a CSV file.

        :param df_ocr_results: The OCR results DataFrame.
        :param file_name: The name for the CSV file (without extension).
        """
        # Get file name from the image path
        file_name = image_path.split('/')[-1].split('.')[0]
        # print("file_name:", file_name) # debugging

        for bbox in df_ocr_results['bbox']:
            (bbox[0][0], bbox[0][1], bbox[1][0], bbox[1][1],
             bbox[2][0], bbox[2][1], bbox[3][0], bbox[3][1]) = (int(bbox[0][0]), int(bbox[0][1]), int(bbox[1][0]), int(bbox[1][1]),
                                                                int(bbox[2][0]), int(bbox[2][1]), int(bbox[3][0]), int(bbox[3][1]))


        csv_name = f'{save_path}/{file_name}.csv'
        df_ocr_results.to_csv(csv_name, index=False)
        print(f'Saved to {csv_name}')


    def draw_boxes(self, image_path, df_ocr_results):
        """
        Draw bounding boxes around the detected text in the image.

        :param image_path: Path to the image file.
        :param df_ocr_results: DataFrame containing OCR results (bbox, text, confidence).
        :return: Image with bounding boxes drawn around the detected text.
        """
        random.seed(0)

        image = cv2.imread(image_path)
        for bbox in df_ocr_results['bbox']:
            rand = random.randint(0, 255)
            # if bbox is a string then use ast.literal_eval to convert it to a list
            if isinstance(bbox, str):
                bbox = ast.literal_eval(bbox)

            cv2.rectangle(image, (int(bbox[0][0]), int(bbox[0][1])), (int(bbox[2][0]), int(bbox[2][1])), (0, 255, 0), 2)

        return image


if __name__ == "__main__":
    random.seed(0)
    # Initialize the OCR processor
    ocr_processor = OCRProcessor()

    # Perform OCR on the given image
    image_path = '../bilder/Briefkaesten.jpg'
    df_ocr_results = ocr_processor.ocr(image_path)
    print(df_ocr_results.head(5))

    save_path = '../csv_speichern'
    # Save the OCR results to a CSV file
    ocr_processor.save_to_csv(df_ocr_results, image_path, save_path)
    print(df_ocr_results)
    # Display the image with bounding boxes
    image = cv2.imread(image_path)
    for bbox in df_ocr_results['bbox']:
        rand = random.randint(100, 200)
        # if bbox is a string then use ast.literal_eval to convert it to a list
        if isinstance(bbox, str):
            bbox = ast.literal_eval(bbox)
        #bbox = ast.literal_eval(bbox) # Use if bbox is from csv file
        print(f'bbox values: {bbox}')

        cv2.rectangle(image, (int(bbox[0][0]), int(bbox[0][1])), (int(bbox[2][0]), int(bbox[2][1])), (0, rand, rand), 3)

    # Reduce the image size for display
    scale_percent = 30# percent of original size
    width = int(3000 * scale_percent / 100)
    height = int(4000 * scale_percent / 100)

    cv2.namedWindow("Image with box", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Image with box", width, height)
    cv2.imshow("Image with box", image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    # plt.figure(figsize=(12, 8))
    # plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    # plt.axis('off')
    # plt.show()