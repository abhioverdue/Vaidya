import torch
import cv2
import numpy as np

MODEL_PATH = r"C:\Users\User\Downloads\Vaidya-gemini\models\computer_vision\hybrid_multitask_model.pth"
IMAGE_PATH = r"test.jpg"  # put ANY image here

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# load model
model = torch.load(MODEL_PATH, map_location=device)
model.to(device)
model.eval()

# preprocess (match your training!)
def preprocess(img_path):
    img = cv2.imread(img_path)
    img = cv2.resize(img, (224, 224))
    img = img / 255.0
    img = np.transpose(img, (2, 0, 1))
    img = torch.tensor(img, dtype=torch.float32)
    return img.unsqueeze(0)

img = preprocess(IMAGE_PATH).to(device)

with torch.no_grad():
    output = model(img, "chest")  # or "skin" / "wound"
    pred = torch.argmax(output, dim=1).item()

print("Prediction:", pred)