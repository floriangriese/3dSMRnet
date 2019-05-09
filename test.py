import os
import sys
import logging
import time
import argparse
import numpy as np
from collections import OrderedDict

import options.options as option
import utils.util as util
from data.util import bgr2ycbcr
from data import create_dataset, create_dataloader
from models import create_model
from engfmt import Quantity

try:
    from tensorboardX import SummaryWriter
    is_tensorboard_available = True
except Exception:
    is_tensorboard_available = False

from timeit import default_timer as timer
def main():
    # options
    parser = argparse.ArgumentParser()
    # TODO Remove
    opt_p = 'E:\\repos\\mpisystemmatrix\\experiments\\007_Test_SR-RRDB-3d_scale4.json'    # JUST FOR TESTIN!!!!!!!
    parser.add_argument('-opt', default=opt_p, type=str, required=False, help='Path to option JSON file.')

    opt = option.parse(parser.parse_args().opt, is_train=False, is_tensorboard_available=is_tensorboard_available)
    opt = option.dict_to_nonedict(opt)

    run_config = opt['run_config']
    optim_config = opt['optim_config']
    data_config = opt['data_config']
    util.mkdirs((path for key, path in run_config['path'].items() if not key == 'pretrain_model_G'))

    # config loggers. Before it, the log will not work
    util.setup_logger(None, run_config['path']['log'], 'test.log', level=logging.INFO, screen=True)
    logger = logging.getLogger('base')
    logger.info(option.dict2str(opt))

    # Create test dataset and dataloader
    test_loaders = []
    for phase, dataset_opt in sorted(data_config.items()):
        test_set = create_dataset(dataset_opt)
        test_loader = create_dataloader(test_set, dataset_opt)
        logger.info('Number of test images in [{:s}]: {:d}'.format(dataset_opt['name'], len(test_set)))
        test_loaders.append(test_loader)

    # Create model
    model = create_model(opt)

    for test_loader in test_loaders:
        test_set_name = test_loader.dataset.opt['name']
        logger.info('\nTesting [{:s}]...'.format(test_set_name))
        test_start_time = time.time()
        dataset_dir = os.path.join(run_config['path']['results_root'], test_set_name)
        util.mkdir(dataset_dir)

        test_results = OrderedDict()

        test_result_dataset = util.HDF5Store(os.path.join(dataset_dir, test_set_name + '_CNNPredict.h5'), (40,40,40,3))
        test_results['time'] = 0
        test_results['ssim'] = []
        test_results['psnr_y'] = []
        test_results['ssim_y'] = []
        need_HR = False
        for idx, data in enumerate(test_loader):
            need_HR = False if test_loader.dataset.opt['dataroot_HR'] is None else True
            start = timer()
            model.feed_data(data, need_HR=need_HR)
            model.test()  # test
            end = timer()
            test_results['time'] += (end - start)
            print(end - start)
            visuals = model.get_current_visuals(need_HR=need_HR)
            sr_imgs = OrderedDict([])
            lr_imgs = OrderedDict([])

            for k in visuals.keys():
                if 'SR' in k:
                    sr_imgs[k] = (util.tensor2img(visuals[k], min_max=None, out_type=np.float32,
                                                  as_grid=False))[np.newaxis, :, :, :, :]  # float32
                if 'LR' in k:
                    lr_imgs[k] = (util.tensor2img(visuals[k], min_max=None, out_type=np.float32,
                                                  as_grid=False))[np.newaxis, :, :, :, :]  # float32
            if need_HR:
                gt_img = util.tensor2img(visuals['HR'], min_max=None, out_type=np.float32,
                                         as_grid=False)[np.newaxis, :, :, :, :]  # float32
            else:
                gt_img = None

            # save images
            for k in sr_imgs.keys():
                img_name = "{0:d}_{1:s}".format(idx, str(Quantity(visuals['hz'].numpy(), 'hz')))
                suffix = opt['suffix']
                if suffix:
                    save_img_path = os.path.join(dataset_dir, img_name + suffix + '.nii.gz')
                else:
                    save_img_path = os.path.join(dataset_dir, img_name + '.nii.gz')

                test_result_dataset.append(sr_imgs[k][0], visuals['hz'])
                if idx % 1 == 0:
                    util.showAndSaveSlice(sr_imgs, lr_imgs, gt_img, save_img_path.replace('.nii.gz', '.png'), slice = test_loader.dataset.opt['LRSize'] // 2,
                                          scale=opt['model_config']['scale'], is_train=False)

            # calculate PSNR and SSIM
            if need_HR:
                # calculate PSNR
                for sr_k in sr_imgs.keys():
                    if 'x' in sr_k:  # find correct key
                        for lr_k in lr_imgs.keys():
                            if sr_k.replace('SR', '') in lr_k:
                                tmp_hr = lr_imgs[lr_k]
                                break
                    else:
                        tmp_hr = gt_img
                    for sr_vol, lr_vol in zip(sr_imgs[sr_k], tmp_hr):
                        mse, rmse, psnr = util.calculate_mse_rmse_psnr(sr_vol, lr_vol)
                        if sr_k in test_results:
                            test_results[sr_k]['mse'].append(mse)
                            test_results[sr_k]['rmse'].append(rmse)
                            test_results[sr_k]['psnr'].append(psnr)
                        else:
                            test_results[sr_k] = OrderedDict([])
                            test_results[sr_k]['mse'] = [mse]
                            test_results[sr_k]['rmse'] = [rmse]
                            test_results[sr_k]['psnr'] = [psnr]
                        logger.info('{:20s} - MSE: {:.6f}; RMSE: {:.6f}; PSNR: {:.6f} dB.'.format(img_name, mse, rmse, psnr))
            else:
                logger.info(img_name)

        print("time: ", test_results['time'])
        if need_HR:  # metrics
            for tr_k in test_results.keys():
                # Average PSNR/SSIM results
                ave_mse = sum(test_results[tr_k]['mse']) / len(test_results[tr_k]['mse'])
                ave_rmse = sum(test_results[tr_k]['rmse']) / len(test_results[tr_k]['rmse'])
                ave_psnr = sum(test_results[tr_k]['psnr']) / len(test_results[tr_k]['psnr'])
                logger.info('----Average PSNR/SSIM results for {} {}----\n\tMSE: {:.6f}; RMSE: {:.6f}; PSNR: {:.6f} dB.\n'\
                        .format(test_set_name, tr_k, ave_mse, ave_rmse, ave_psnr))



if __name__ == "__main__":
    main()
