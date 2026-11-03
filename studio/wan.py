"""Base clips with Wan 2.2 TI2V-5B (GGUF Q8) on a 16 GB GPU: one ~5 s take per seed, from one start frame.

  python wan.py --image start.png --prompt prompt.txt --negative negative.txt --seeds 42 7 --out takes/

A take that already has its mp4 is skipped, so re-running resumes. Latents are saved before decoding, so a
crash in the decode loses no generation time.
"""

import argparse
import gc
import os
import time
from pathlib import Path

import torch
from diffusers import AutoencoderKLWan, GGUFQuantizationConfig, WanImageToVideoPipeline, WanTransformer3DModel
from diffusers.utils import export_to_video
from huggingface_hub import HfApi, hf_hub_download
from PIL import Image
from transformers import AutoTokenizer, BitsAndBytesConfig, UMT5EncoderModel

BASE = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
DTYPE = torch.float16  # T4/P100 have no fast bf16
WIDTH, HEIGHT = 480, 832
NUM_FRAMES, FPS = 121, 24


def encode_prompt(prompt, negative):
    # 8-bit text encoder, freed straight after so the video model has the GPU to itself
    tokenizer = AutoTokenizer.from_pretrained(BASE, subfolder="tokenizer")
    text_encoder = UMT5EncoderModel.from_pretrained(
        BASE, subfolder="text_encoder", quantization_config=BitsAndBytesConfig(load_in_8bit=True),
        torch_dtype=DTYPE, device_map={"": 0}, low_cpu_mem_usage=True,
    )
    te = WanImageToVideoPipeline.from_pretrained(
        BASE, tokenizer=tokenizer, text_encoder=text_encoder, transformer=None, vae=None,
        image_encoder=None, image_processor=None, torch_dtype=DTYPE,
    )
    with torch.no_grad():
        pe, ne = te.encode_prompt(
            prompt=prompt, negative_prompt=negative, do_classifier_free_guidance=True,
            num_videos_per_prompt=1, max_sequence_length=512, device="cuda",
        )
    del te, text_encoder
    gc.collect()
    torch.cuda.empty_cache()
    return pe.to("cpu", DTYPE), ne.to("cpu", DTYPE)


def load_pipe():
    api = HfApi()
    repo = file = None
    for m in api.list_models(search="Wan2.2-TI2V-5B-GGUF", sort="downloads", limit=10):
        pick = [f for f in api.list_repo_files(m.id) if f.endswith(".gguf") and "Q8_0" in f]
        if pick:
            repo, file = m.id, pick[0]
            break
    assert repo, "No Wan2.2-TI2V-5B GGUF found on the Hub"
    print("video model:", repo, file, flush=True)
    transformer = WanTransformer3DModel.from_single_file(
        hf_hub_download(repo, file), quantization_config=GGUFQuantizationConfig(compute_dtype=DTYPE),
        config=BASE, subfolder="transformer", torch_dtype=DTYPE,
    )
    vae = AutoencoderKLWan.from_pretrained(BASE, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanImageToVideoPipeline.from_pretrained(
        BASE, transformer=transformer, vae=vae, text_encoder=None, tokenizer=None,
        image_encoder=None, image_processor=None, torch_dtype=DTYPE,
    )
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    return pipe


def decode(pipe, latents):
    v = pipe.vae.to("cuda", torch.float16)
    lat = latents.to("cuda", torch.float16)
    mean = torch.tensor(v.config.latents_mean).view(1, v.config.z_dim, 1, 1, 1).to(lat)
    inv_std = 1.0 / torch.tensor(v.config.latents_std).view(1, v.config.z_dim, 1, 1, 1).to(lat)
    with torch.no_grad():
        video = v.decode(lat / inv_std + mean, return_dict=False)[0]
    v.to("cpu")
    torch.cuda.empty_cache()
    return pipe.video_processor.postprocess_video(video.float(), output_type="np")[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = [s for s in args.seeds if not (out / f"take_seed{s}.mp4").exists()]
    if not todo:
        print("all takes already made")
        return
    img = Image.open(args.image).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    pe, ne = encode_prompt(Path(args.prompt).read_text(), Path(args.negative).read_text())
    pipe = load_pipe()

    for seed in todo:
        t0 = time.time()
        lat_path = out / f"latents_seed{seed}.pt"
        print(f"take seed {seed}: generating ({args.steps} steps)...", flush=True)
        if not lat_path.exists():
            with torch.no_grad():
                lat = pipe(
                    image=img, prompt_embeds=pe.to("cuda"), negative_prompt_embeds=ne.to("cuda"),
                    height=HEIGHT, width=WIDTH, num_frames=NUM_FRAMES, num_inference_steps=args.steps,
                    guidance_scale=args.guidance, generator=torch.Generator("cuda").manual_seed(seed),
                    output_type="latent",
                ).frames
            torch.save(lat.cpu(), lat_path)
        export_to_video(decode(pipe, torch.load(lat_path)), str(out / f"take_seed{seed}.mp4"), fps=FPS)
        os.remove(lat_path)
        print(f"take seed {seed}: done in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
