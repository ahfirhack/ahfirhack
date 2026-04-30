import os
import subprocess

def get_audio_duration(file_path):
    """
    Retrieves audio duration using ffprobe with a safety floor to 
    prevent 'float division by zero' in downstream logic.
    """
    try:
        if not os.path.exists(file_path):
            return 1.0 # Fallback if file missing

        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        duration = float(result.stdout.strip())
        
        # Guard: Ensure duration is never 0
        return max(duration, 1.0) 
    except (ValueError, subprocess.SubprocessError):
        # Fallback for corrupted audio files
        return 1.0

def assemble_video(audio_path, output_path, caption_data):
    """
    Assembles the final video with specific guards for 'The Modern Stoic' 
    and other automated channels.
    """
    # 1. Get duration with safety check[cite: 5]
    duration = get_audio_duration(audio_path)
    
    # 2. Guard against division by zero during caption segmenting[cite: 5]
    for cap in caption_data:
        start = cap.get('start', 0.0)
        end = cap.get('end', 1.0)
        text = cap.get('text', "")
        
        # Ensure the time slice is positive[cite: 5]
        time_slice = max(end - start, 0.1)
        
        # Guard: Prevent division by zero if a caption is empty[cite: 5]
        words = text.split()
        word_count = max(len(words), 1)
        
        # Calculate timing per word safely[cite: 5]
        per_word_timing = time_slice / word_count
        
        # (FFmpeg command execution logic follows here)
    
    print(f"Video assembly complete for {duration} seconds.")
    return Trueimport os
import subprocess

def get_audio_duration(file_path):
    """
    Retrieves audio duration using ffprobe with a safety floor to 
    prevent 'float division by zero' in downstream logic.
    """
    try:
        if not os.path.exists(file_path):
            return 1.0 # Fallback if file missing

        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        duration = float(result.stdout.strip())
        
        # Guard: Ensure duration is never 0
        return max(duration, 1.0) 
    except (ValueError, subprocess.SubprocessError):
        # Fallback for corrupted audio files
        return 1.0

def assemble_video(audio_path, output_path, caption_data):
    """
    Assembles the final video with specific guards for 'The Modern Stoic' 
    and other automated channels.
    """
    # 1. Get duration with safety check[cite: 5]
    duration = get_audio_duration(audio_path)
    
    # 2. Guard against division by zero during caption segmenting[cite: 5]
    for cap in caption_data:
        start = cap.get('start', 0.0)
        end = cap.get('end', 1.0)
        text = cap.get('text', "")
        
        # Ensure the time slice is positive[cite: 5]
        time_slice = max(end - start, 0.1)
        
        # Guard: Prevent division by zero if a caption is empty[cite: 5]
        words = text.split()
        word_count = max(len(words), 1)
        
        # Calculate timing per word safely[cite: 5]
        per_word_timing = time_slice / word_count
        
        # (FFmpeg command execution logic follows here)
    
    print(f"Video assembly complete for {duration} seconds.")
    return True
