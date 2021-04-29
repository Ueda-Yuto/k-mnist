import os
import random

import numpy as np
import pandas as pd
import cv2

import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import SGD,Adam
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as transforms
# from torchvision import models
from tqdm import tqdm_notebook as tqdm

%matplotlib inline

def seed_everything(seed=42):
    os.environ['PYTHONHASHSEED'] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True

INPUT_DIR = '../input/sugiura-lab-first-competition/'

PATH = {
    'train': os.path.join(INPUT_DIR, 'train.csv'),
    'sample_submission': os.path.join(INPUT_DIR, 'sample_submission.csv'),
    'train_image_dir': os.path.join(INPUT_DIR, 'train_images/train_images'),
    'test_image_dir': os.path.join(INPUT_DIR, 'test_images/test_images'),
}

ID = 'fname'
TARGET = 'label'

SEED = 42
seed_everything(SEED)

# GPU settings for PyTorch (explained later...)
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

# Parameters for neural network. We will see the details later...
PARAMS = {
    'valid_size': 0.1,
    'batch_size': 64,
    'epochs':  50,
    'lr': 0.001,
    'valid_batch_size': 256,
    'test_batch_size': 256,
}

train_df = pd.read_csv(PATH['train'])
sample_submission_df = pd.read_csv(PATH['sample_submission'])

print(f'number of train data: {len(train_df)}')
print(f'number of test data: {len(sample_submission_df)}')

print(f'number of unique label: {train_df[TARGET].nunique()}')

sns.countplot(train_df[TARGET])
plt.title('train label distribution')
plt.show()

train_df.head()

sample = train_df.groupby(TARGET).first().reset_index()

fig, ax = plt.subplots(2, 5)
fig.set_size_inches(4 * 5, 4 * 2)

for i, row in sample.iterrows():
    fname, label = row[ID], row[TARGET]
    img = cv2.imread(os.path.join(PATH['train_image_dir'], fname))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ax[i//5,i%5].imshow(img, 'gray')
    ax[i//5,i%5].set_title(f'{fname} - label: {label}')

print(f'shape of image: {img.shape}')

class KMNISTDataset(Dataset):
    def __init__(self, fname_list, label_list, image_dir, transform=None):
        super().__init__()
        self.fname_list = fname_list
        self.label_list = label_list
        self.image_dir = image_dir
        self.transform = transform


    def __len__(self):
        return len(self.fname_list)

    def __getitem__(self, idx):
        fname = self.fname_list[idx]
        label = self.label_list[idx]

        image = cv2.imread(os.path.join(self.image_dir, fname))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.transform is not None:
            image = self.transform(image)

        return image, label

# 10-classification
# input: 28*28(grayscale) output: the class in 10 classes

class MLP(nn.Module):
    def __init__(self, input_dim=28*28, hidden_dim=128, output_dim=10):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, output_dim)
        self.activation = nn.ReLU()

    def forward(self, x):
        x = x.view(x.size(0), -1)
        x = self.fc1(x)
        x = self.activation(x)
        x = self.fc2(x)

        return x


class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()

        self.conv1 = nn.Conv2d(1, 32, 5, padding=2)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=2)
        self.conv3 = nn.Conv2d(64, 128, 3, padding=2)
        self.maxpool = nn.MaxPool2d(2, stride=2)
        self.fc1 = nn.Linear(128*5*5, 1024)
        self.fc2 = nn.Linear(1024, 256)
        self.fc3 = nn.Linear(256, 64)
        self.fc4 = nn.Linear(64, 16)
        self.fc5 = nn.Linear(16, 10)

    def forward(self, x):
        batch_size = x.shape[0]
        x = self.conv1(x)
        x = F.relu6(x)
        x = self.maxpool(x)
        x = self.conv2(x)
        x = F.relu6(x)
        x = self.maxpool(x)
        x = self.conv3(x)
        x = F.relu6(x)
        x = self.maxpool(x)
        x = x.view(batch_size, -1)
        x = self.fc1(x)
        x = self.fc2(x)
        x = self.fc3(x)
        x = self.fc4(x)
        x = self.fc5(x)
        x = F.relu6(x)
        return x


net = Net()


train_df, valid_df = train_test_split(
    train_df, test_size=PARAMS['valid_size'], random_state=SEED, shuffle=True
)
train_df = train_df.reset_index(drop=True)
valid_df = valid_df.reset_index(drop=True)


transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.5, ), (0.5, ))
])

train_dataset = KMNISTDataset(train_df[ID], train_df[TARGET], PATH['train_image_dir'], transform=transform)
valid_dataset = KMNISTDataset(valid_df[ID], valid_df[TARGET], PATH['train_image_dir'], transform=transform)

train_dataloader = DataLoader(train_dataset, batch_size=PARAMS['batch_size'], shuffle=True)
valid_dataloader = DataLoader(valid_dataset, batch_size=PARAMS['valid_batch_size'], shuffle=False)

model = Net().to(DEVICE)

optim = Adam(model.parameters(), lr=PARAMS['lr'])
criterion = nn.CrossEntropyLoss()

def accuracy_score_torch(y_pred, y):
    y_pred = torch.argmax(y_pred, axis=1).cpu().numpy()
    y = y.cpu().numpy()

    return accuracy_score(y_pred, y)

state_dicts = []

for epoch in range(PARAMS['epochs']):
    model.train()
    train_loss_list = []
    train_accuracy_list = []

    for x, y in tqdm(train_dataloader):
        x = x.to(dtype=torch.float32, device=DEVICE)
        y = y.to(dtype=torch.long, device=DEVICE)

        optim.zero_grad()
        y_pred = model(x)
        loss = criterion(y_pred, y)
        loss.backward()
        optim.step()

        train_loss_list.append(loss.item())
        train_accuracy_list.append(accuracy_score_torch(y_pred, y))

    model.eval()
    valid_loss_list = []
    valid_accuracy_list = []

    for x, y in tqdm(valid_dataloader):
        x = x.to(dtype=torch.float32, device=DEVICE)
        y = y.to(dtype=torch.long, device=DEVICE)

        with torch.no_grad():
            y_pred = model(x)
            loss = criterion(y_pred, y)

        valid_loss_list.append(loss.item())
        valid_accuracy_list.append(accuracy_score_torch(y_pred, y))

    print('epoch: {}/{} - loss: {:.5f} - accuracy: {:.3f} - val_loss: {:.5f} - val_accuracy: {:.3f}'.format(
        epoch,
        PARAMS['epochs'], 
        np.mean(train_loss_list),
        np.mean(train_accuracy_list),
        np.mean(valid_loss_list),
        np.mean(valid_accuracy_list)
    ))
    if epoch == 0:
        best_score = np.mean(valid_accuracy_list)
        best_sd = model.state_dict

    if np.mean(valid_accuracy_list) > best_score:
        best_score = np.mean(valid_accuracy_list)
        best_sd = model.state_dict()

    if epoch > 10:
        PARAMS['lr'] /= 2

state_dicts.append(best_sd)
torch.save(best_sd, 'model')

transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.5, ), (0.5, ))
])

test_dataset = KMNISTDataset(
    sample_submission_df[ID],
    sample_submission_df[TARGET],
    PATH['test_image_dir'],
    transform=transform
)

test_dataloader = DataLoader(test_dataset, batch_size=PARAMS['test_batch_size'], shuffle=False)

predictions = np.zeros((len(sample_submission_df), 10))

for state_dict in state_dicts:
    model = Net().to(DEVICE)
    model.eval()
    model.load_state_dict(state_dict)
    preds = []

    for x, _ in test_dataloader:
        x = x.to(dtype=torch.float32, device=DEVICE)

        with torch.no_grad():
            y_pred = model(x)
            preds.append(y_pred.cpu().numpy())

    preds = np.concatenate(preds)
    predictions += preds / len(state_dicts)

sample_submission_df[TARGET] = predictions

sample_submission_df.to_csv('submission.csv', index=False)
from IPython.display import FileLink
FileLink('submission.csv')

sns.countplot(sample_submission_df[TARGET])
plt.title('test prediction label distribution')
plt.show()

fig, ax = plt.subplots(2, 5)
fig.set_size_inches(4 * 5, 4 * 2)

for i, row in sample_submission_df.iloc[:10,:].iterrows():
    fname, label = row[ID], row[TARGET]
    img = cv2.imread(os.path.join(PATH['test_image_dir'], fname))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ax[i//5,i%5].imshow(img, 'gray')
    ax[i//5,i%5].set_title(f'{fname} - label: {label}')