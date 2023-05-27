import os.path
import torch
import torchaudio
from bark.generation import SAMPLE_RATE, load_codec_model

from hubert.customtokenizer import CustomTokenizer
from hubert.hubert_manager import HuBERTManager
from hubert.pre_kmeans_hubert import CustomHubert
from webui.modules.implementations.patches.bark_generation import generate_text_semantic_new, generate_coarse_new, generate_fine_new
from encodec.utils import convert_audio
from webui.args import args


def generate_semantic_fine(transcript='There actually isn\'t a way to do that. It\'s impossible. Please don\'t even bother.'):
    """
    Creates a speech file with semantics and fine audio
    :param transcript: The transcript.
    :return: tuple with (semantic, fine)
    """
    semantic = generate_text_semantic_new(transcript)  # We need speech patterns
    coarse = generate_coarse_new(semantic)  # Voice doesn't matter
    fine = generate_fine_new(coarse)  # Good audio, ready for what comes next
    return semantic, fine


huberts = {}


def load_hubert():
    hubert_path = HuBERTManager.make_sure_hubert_installed()
    model = ('quantifier_V1_hubert_base_ls960_23.pth', 'tokenizer_large.pth') if args.bark_cloning_large_model else ('quantifier_hubert_base_ls960_14.pth', 'tokenizer.pth')
    tokenizer_path = HuBERTManager.make_sure_tokenizer_installed(model=model[0], local_file=model[1])
    if 'hubert' not in huberts:
        print('Loading HuBERT')
        huberts['hubert'] = CustomHubert(hubert_path)
    if 'tokenizer' not in huberts:
        print('Loading Custom Tokenizer')
        tokenizer = CustomTokenizer.load_from_checkpoint(tokenizer_path, map_location=torch.device('cpu'))
        huberts['tokenizer'] = tokenizer


def wav_to_semantics(file) -> torch.Tensor:
    # Vocab size is 10,000.

    load_hubert()

    wav, sr = torchaudio.load(file)
    # sr, wav = wavfile.read(file)
    # wav = torch.tensor(wav, dtype=torch.float32)

    if wav.shape[0] == 2:  # Stereo to mono if needed
        wav = wav.mean(0, keepdim=True)

    # Extract semantics in HuBERT style
    print('Extracting semantics')
    semantics = huberts['hubert'].forward(wav, input_sample_hz=sr)
    print('Tokenizing semantics')
    tokens = huberts['tokenizer'].get_token(semantics)
    return tokens


def eval_semantics(code):
    """
    BE CAREFUL, this will execute :code:
    :param code: The code to evaluate, out local will be used for the output.
    :return: The created numpy array.
    """
    _locals = locals()
    exec(code, globals(), _locals)
    return _locals['out']


def generate_course_history(fine_history):
    return fine_history[:2, :]


def generate_fine_from_wav(file):
    model = load_codec_model(use_gpu=not args.bark_use_cpu)  # Don't worry about reimporting, it stores the loaded model in a dict
    wav, sr = torchaudio.load(file)
    wav = convert_audio(wav, sr, SAMPLE_RATE, model.channels)
    wav = wav.unsqueeze(0)
    if not (args.bark_cpu_offload or args.bark_use_cpu):
        wav = wav.to('cuda')
    with torch.no_grad():
        encoded_frames = model.encode(wav)
    codes = torch.cat([encoded[0] for encoded in encoded_frames], dim=-1).squeeze()

    codes = codes.cpu().numpy()

    return codes

