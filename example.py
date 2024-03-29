from diffusers import DDPMScheduler, UNet2DModel
from PIL import Image
import torch
"""
Train a diffusion model on images.
"""

import argparse
import os
import math
import torch
import time
from PIL import Image
import torchvision as tv
from guided_diffusion import dist_util, logger
from guided_diffusion.image_datasets import load_data
from guided_diffusion.resample import create_named_schedule_sampler
from guided_diffusion.script_util import (
    model_and_diffusion_defaults,
    create_model_and_diffusion,
    args_to_dict,
    add_dict_to_argparser,
    adjust_scales2image
)
from guided_diffusion.train_util import TrainLoop, parse_resume_step_from_filename


def main():
    args = create_argparser().parse_args()

    dist_util.setup_dist()
    logger.configure()

    real = tv.transforms.ToTensor()(Image.open(args.data_dir))[None]
    adjust_scales2image(real, args)

    logger.configure(dir='output/train')

    logger.log("creating model and diffusion...")
    model, diffusion = create_model_and_diffusion(
        **args_to_dict(args, model_and_diffusion_defaults().keys())
    )
    model.to(dist_util.dev())
    schedule_sampler = create_named_schedule_sampler(args.schedule_sampler, diffusion)
    
    # model = torch.compile(model)

    logger.log("creating data loader...")
    data = load_data(
        data_dir=args.data_dir,
        batch_size=args.batch_size,
        image_size=args.image_size,
        class_cond=args.class_cond,
        random_crop=False,
        random_flip=False,
        scale_init=args.scale1,
        scale_factor=args.scale_factor,
        stop_scale=args.stop_scale,
        current_scale=args.stop_scale
    )

    logger.log("training...")
    trainer = TrainLoop(
        model=model,
        diffusion=diffusion,
        data=data,
        batch_size=args.batch_size,
        microbatch=args.microbatch,
        lr=args.lr,
        ema_rate=args.ema_rate,
        log_interval=args.log_interval,
        save_interval=args.save_interval,
        resume_checkpoint=args.resume_checkpoint,
        use_fp16=args.use_fp16,
        fp16_scale_growth=args.fp16_scale_growth,
        schedule_sampler=schedule_sampler,
        weight_decay=args.weight_decay,
        lr_anneal_steps=args.lr_anneal_steps,
        )
    trainer.run_loop()
    
    # scheduler = DDPMScheduler.from_pretrained("google/ddpm-cat-256")
    # # model = UNet2DModel.from_pretrained("google/ddpm-cat-256").to("cuda")
    # scheduler.set_timesteps(50)

    # sample_size = args.image_size
    # noise = torch.randn((1, 3, sample_size, sample_size), device="cuda")
    # input = noise

    # for t in scheduler.timesteps:
    #     with torch.no_grad():
    #         noisy_residual = model(input, t).sample
    #         prev_noisy_sample = scheduler.step(noisy_residual, t, input).prev_sample
    #         input = prev_noisy_sample

    # image = (input / 2 + 0.5).clamp(0, 1)
    # image = image.cpu().permute(0, 2, 3, 1).numpy()[0]
    # image = Image.fromarray((image * 255).round().astype("uint8"))
    # image


def create_argparser():
    defaults = dict(
        data_dir="",
        schedule_sampler="uniform",
        lr=1e-4,
        weight_decay=0.0,
        lr_anneal_steps=50000,
        num_channels_init=128,
        num_res_blocks_init=6,
        scale_factor_init=0.75,
        min_size=25,
        max_size=250,
        nc_im=3,
        batch_size=1,
        microbatch=-1,  # -1 disables microbatches
        ema_rate="0.9999",  # comma-separated list of EMA values
        log_interval=10,
        save_interval=10000,
        resume_checkpoint="",
        use_fp16=False,
        fp16_scale_growth=1e-3,
    )
    config = dict(
        diffusion_steps=1000, 
        noise_schedule='linear',
        channel_mult="1,2,4",
        use_checkpoint=True,
        use_scale_shift_norm=True,
        use_fp16=True,
        num_channels=64,
        num_head_channels=16,
        num_res_blocks=1,
        resblock_updown=False,
        attention_resolutions="2",
    )
    defaults.update(model_and_diffusion_defaults())
    defaults.update(config)
    parser = argparse.ArgumentParser()
    add_dict_to_argparser(parser, defaults)
    return parser


if __name__ == "__main__":
    main()


