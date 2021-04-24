
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import os
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np

from sklearn.metrics import classification_report, roc_auc_score, roc_curve, confusion_matrix


def read_txt(txt_path):
    with open(txt_path) as f:
        lines = f.readlines()
    txt_data = [line.strip() for line in lines]
    return txt_data


class CTXDataset(Dataset):
    def __init__(self, root_dir, classes, splitfile, transform=None):
        self.root_dir = root_dir
        self.classes = classes
        self.split_file = splitfile

        files = read_txt(self.split_file)
        images = []
        for file in files:
            img_name = file.split(" ")[0]
            if "NCP" in img_name or "Normal" in img_name:
                images.append((os.path.join(self.root_dir, img_name), 0))
            else:
                images.append([os.path.join(self.root_dir, img_name), 1])

        self.image_list = np.array(images)

        self.transform = transform

    def __len__(self):
        return len(self.image_list)

    def __getitem__(self, idx):
        path = self.image_list[idx][0]

        # Read the image
        image = Image.open(path).convert('RGB')

        # Apply transforms
        if self.transform:
            image = self.transform(image)

        label = int(self.image_list[idx][1])

        data = {'img': image,
                'label': label,
                'paths': path}

        return data


def compute_metrics(model, test_loader, device, plot_roc_curve=False):
    model.eval()

    val_loss = 0
    val_correct = 0

    criterion = nn.CrossEntropyLoss()

    score_list = torch.Tensor([]).to(device)
    pred_list = torch.Tensor([]).to(device).long()
    target_list = torch.Tensor([]).to(device).long()
    path_list = []

    for iter_num, data in enumerate(test_loader):
        # Convert image data into single channel data
        image, target = data['img'].to(device), data['label'].to(device)
        paths = data['paths']
        path_list.extend(paths)

        # Compute the loss
        with torch.no_grad():
            output = model(image)

        # Log loss
        val_loss += criterion(output, target.long()).item()

        # Calculate the number of correctly classified examples
        pred = output.argmax(dim=1, keepdim=True)
        val_correct += pred.eq(target.long().view_as(pred)).sum().item()

        # Bookkeeping
        # score_list = torch.cat([score_list, nn.Softmax(dim=1)(output)[:, 1].squeeze()])
        score_list = torch.cat([score_list, nn.Softmax(dim=1)(output)[:, 0].squeeze()])
        pred_list = torch.cat([pred_list, pred.squeeze()])
        target_list = torch.cat([target_list, target.squeeze()])

    classification_metrics = classification_report(target_list.tolist(), pred_list.tolist(),
                                                   target_names=['CT_NonCOVID', 'CT_COVID'],
                                                   # target_names=['CT_COVID'],
                                                   output_dict=True)

    # sensitivity is the recall of the positive class
    # sensitivity = classification_metrics['CT_COVID']['recall']

    # specificity is the recall of the negative class
    # specificity = classification_metrics['CT_NonCOVID']['recall']

    # accuracy
    accuracy = classification_metrics['accuracy']

    # confusion matrix
    conf_matrix = confusion_matrix(target_list.tolist(), pred_list.tolist())

    # roc score
    roc_score = roc_auc_score(target_list.tolist(), score_list.tolist())

    # plot the roc curve
    if plot_roc_curve:
        fpr, tpr, _ = roc_curve(target_list.tolist(), score_list.tolist())
        plt.plot(fpr, tpr, label="Area under ROC = {:.4f}".format(roc_score))
        plt.legend(loc='best')
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.show()

    # put together values
    metrics_dict = {
                    "Accuracy": accuracy,
                    # "Sensitivity": sensitivity,
                    # "Specificity": specificity,
                    "Roc_score": roc_score,
                    "Confusion Matrix": conf_matrix,
                    "Validation Loss": val_loss / len(test_loader),
                    "score_list": score_list.tolist(),
                    "pred_list": pred_list.tolist(),
                    "target_list": target_list.tolist(),
                    "paths": path_list}

    return metrics_dict