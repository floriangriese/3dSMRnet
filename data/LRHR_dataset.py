import os.path
import random
import numpy as np
import cv2
import torch
import torch.utils.data as data
import data.util as util
from collections import OrderedDict
import h5py
import numpy as np
import logging

#TODO: Change to only load single LRHR pair
class LRHRDataset(data.Dataset):
    '''
    Read LR and HR image pairs.
    If only HR image is provided, generate LR image on-the-fly.
    The pair is ensured by 'sorted' function, so please check the name convention.
    '''

    def __init__(self, opt, ):
        super(LRHRDataset, self).__init__()
        self.logger = logging.getLogger('base')
        self.opt = opt

        self.HR_hdf5 = OrderedDict() if opt['dataroot_HR'] else None
        self.LR_hdf5 = OrderedDict()

        # read SM from hdf5 file
        if self.HR_hdf5 is not None:
            with h5py.File(opt['dataroot_HR']) as hf:
                self.logger.info('Read hdf5: {}'.format(opt['dataroot_HR']))
                for key, value in hf.items():
                    self.HR_hdf5[key] = np.array(value)
            assert len(self.HR_hdf5) > 0, 'Error: HR is empty.'

        with h5py.File(opt['dataroot_LR']) as hf:
            self.logger.info('Read hdf5: {}'.format(opt['dataroot_LR']))
            for key, value in hf.items():
                self.LR_hdf5[key] = np.array(value)
        assert len(self.LR_hdf5) > 0, 'Error: LR is empty.'

        self.LR_hdf5['data'] = np.array(self.LR_hdf5['data']) - 236.17393  # input norm
        if self.LR_hdf5['data'].shape[1] == 3:
            # convert data to BGR, F HWDC
            self.LR_hdf5['data'] = np.transpose( self.LR_hdf5['data'][:, [2, 1, 0], :, :, :], [0, 2, 3, 4, 1])

        if self.HR_hdf5 is not None:
            if self.HR_hdf5['data'].shape[1] == 3:
                # convert data to BGR, F HWDC
                self.HR_hdf5['data'] = np.transpose(self.HR_hdf5['data'][:, [2, 1, 0], :, :, :], [0, 2, 3, 4, 1])
            if 'data' in self.HR_hdf5 and 'data' in self.LR_hdf5:
                assert len(self.HR_hdf5['data'])  == len(self.LR_hdf5['data']), \
                    'HR and LRx2 and LRx4 datasets have different number of images - {}, {}.'.format(
                    len(self.HR_hdf5['data']), len(self.LR_hdf5['data']))

        self.random_scale_list = [1]

    def __getitem__(self, index):
        # get HR image
        # load frequence as BGR, HWDC
        img_HR = self.HR_hdf5['data'][index] if self.HR_hdf5 else None

        if 'data' in self.LR_hdf5:
            img_LR = self.LR_hdf5['data'][index]

        if self.opt['phase'] == 'train':
            # augmentation - flip, rotate
            img_LR, img_HR = util.augment(
                [img_LR, img_HR], self.opt['use_flip'], self.opt['use_rot']
            )

        # BGR to RGB,
        if self.HR_hdf5:
            if img_HR.shape[3] == 3:
                img_HR = img_HR[:, :, :, [2, 1, 0]]
            # HWC to CHW, numpy to tensor
            img_HR = torch.from_numpy(np.ascontiguousarray(np.transpose(img_HR, (3, 0, 1, 2)))).float()

        # BGR to RGB,
        if img_LR.shape[3] == 3:
            img_LR = img_LR[:, :, :, [2, 1, 0]]
        img_LR = torch.from_numpy(np.ascontiguousarray(np.transpose(img_LR, (3, 0, 1, 2)))).float()

        if self.HR_hdf5:
            return {'LR': img_LR, 'HR': img_HR, 'hz': self.LR_hdf5['hz'][index]}
        else:
            return {'LR': img_LR, 'hz': self.LR_hdf5['hz'][index]}

    def __len__(self):
        return len(self.LR_hdf5['data'])
