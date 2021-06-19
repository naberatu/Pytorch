from os.path import splitext
from os import listdir
import numpy as np
from glob import glob
import torch
from torch.utils.data import Dataset
import logging
from PIL import Image

import sys
import matplotlib
from matplotlib import pyplot as plt
from matplotlib import cm


class SegSet(Dataset):
    def __init__(self, imgs_dir, masks_dir, scale=1, mask_suffix='', trs=None):
        self.imgs_dir = imgs_dir
        self.masks_dir = masks_dir
        self.scale = scale
        self.mask_suffix = mask_suffix
        self.transforms = trs
        self.mapping = {
            0: 0,       # Black      (Background)
            150: 1,     # Dark Gray  (Ground-Glass)
            255: 2,     # Pure White (Consolidation)
            104: 3,     # Light Gray (Pleural Effusion)
        }
        assert 0 < scale <= 1, 'Scale must be between 0 and 1'

        self.ids = [splitext(file)[0] for file in listdir(imgs_dir)
                    if not file.startswith('.')]
        logging.info(f'Creating dataset with {len(self.ids)} examples')

    def __len__(self):
        return len(self.ids)

    def mapToRGB(self, mask):
        class_mask = mask
        h, w = class_mask.shape[1], class_mask.shape[2]

        classes = 4 - 1

        idx = np.linspace(0., 1., classes)
        cmap = cm.get_cmap('viridis')
        rgb = cmap(idx, bytes=True)[:, :3]  # Remove alpha value

        rgb = rgb.repeat(1000, 0)
        target = np.zeros((h * w, 3), dtype=np.uint8)
        target[:rgb.shape[0]] = rgb
        target = target.reshape(h, w, 3)

        target = torch.from_numpy(target)
        colors = torch.unique(target.view(-1, target.size(2)), dim=0).numpy()
        # target = target.permute(2, 0, 1).contiguous()

        mapping = {tuple(c): t for c, t in zip(colors.tolist(), range(len(colors)))}

        mask_out = torch.empty(h, w, dtype=torch.long)          # Creates empty template tensor

        for k in mapping:            # <--- May be the culprit with distinctions (but maybe not?).
            idx = (class_mask == torch.tensor(k, dtype=torch.uint8).unsqueeze(1).unsqueeze(2))
            validx = (idx.sum(0) == 3)
            mask_out[validx] = torch.tensor(mapping[k], dtype=torch.long)  # Fills in tensor

        return mask_out

    @classmethod
    def preprocess(cls, pil_img, scale, transforms=None):
        w, h = pil_img.size
        newW, newH = int(scale * w), int(scale * h)
        assert newW > 0 and newH > 0, 'Scale is too small'
        pil_img = pil_img.resize((newW, newH))

        if transforms:
            pil_img = transforms(pil_img)

        img_nd = np.array(pil_img)

        if len(img_nd.shape) == 2:
            img_nd = np.expand_dims(img_nd, axis=2)

        # Reorders dimensions from H, W, C to C, H, W
        img_trans = img_nd
        if img_nd.shape != (3, newH, newW):
            img_trans = img_nd.transpose((2, 0, 1))

        if img_trans.max() > 1:
            img_trans = img_trans / 255

        return img_trans

    def __getitem__(self, i):
        idx = self.ids[i]
        mask_file = glob(self.masks_dir + idx + self.mask_suffix + '.*')
        img_file = glob(self.imgs_dir + idx + '.*')

        assert len(mask_file) == 1, \
            f'Either no mask or multiple masks found for the ID {idx}: {mask_file}'
        assert len(img_file) == 1, \
            f'Either no image or multiple images found for the ID {idx}: {img_file}'
        mask = Image.open(mask_file[0])
        img = Image.open(img_file[0])

        assert img.size == mask.size, \
            f'Image and mask {idx} should be the same size, but are {img.size} and {mask.size}'

        img = self.preprocess(img, self.scale, transforms=self.transforms)
        mask = self.preprocess(mask, self.scale)

        img = torch.from_numpy(img).type(torch.FloatTensor)
        mask = torch.from_numpy(mask).type(torch.FloatTensor)

        mask = self.mapToRGB(mask).float()



        return {
            'image': img,
            'mask': mask
        }
