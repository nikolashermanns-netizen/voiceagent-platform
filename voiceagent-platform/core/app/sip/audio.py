"""
Audio-Resampling Pipeline fuer VoiceAgent Platform.

Konvertiert Audio zwischen verschiedenen Sample-Rates:
- SIP/PJSIP: 48kHz (Opus)
- OpenAI Input: 16kHz
- OpenAI Output: 24kHz
"""

import logging

import numpy as np
from scipy import signal as scipy_signal

from core.app.config import settings

logger = logging.getLogger(__name__)


def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    """
    Resampelt PCM16 Audio von einer Sample-Rate zur anderen.

    Args:
        audio_data: PCM16 Audio-Daten (16-bit signed, little-endian)
        from_rate: Quell-Sample-Rate (z.B. 48000)
        to_rate: Ziel-Sample-Rate (z.B. 16000)

    Returns:
        Resampled PCM16 Audio-Daten
    """
    if from_rate == to_rate:
        return audio_data

    # Bytes zu numpy array (16-bit signed)
    samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)

    # Resampling
    num_samples = int(len(samples) * to_rate / from_rate)
    resampled = scipy_signal.resample(samples, num_samples)

    # Zurueck zu 16-bit signed
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)

    return resampled.tobytes()


def sip_to_ai_input(audio_data: bytes) -> bytes:
    """
    Konvertiert Audio von SIP (48kHz) zu AI Input (16kHz).

    Args:
        audio_data: PCM16 @ 48kHz

    Returns:
        PCM16 @ 16kHz
    """
    return resample_audio(
        audio_data,
        settings.SAMPLE_RATE_SIP,
        settings.SAMPLE_RATE_AI_INPUT
    )


def ai_output_to_sip(audio_data: bytes) -> bytes:
    """
    Konvertiert Audio von AI Output (24kHz) zu SIP (48kHz).

    Args:
        audio_data: PCM16 @ 24kHz

    Returns:
        PCM16 @ 48kHz
    """
    return resample_audio(
        audio_data,
        settings.SAMPLE_RATE_AI_OUTPUT,
        settings.SAMPLE_RATE_SIP
    )
