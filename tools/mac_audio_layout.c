/* Read-only ABI receipt from the installed Apple SDK; never opens an audio device. */
#include <AudioToolbox/AudioToolbox.h>
#include <stddef.h>
#include <stdio.h>

int main(void) {
    printf("{\"stream_bytes\":%zu,\"buffer_bytes\":%zu,"
           "\"buffer_data_offset\":%zu,\"buffer_size_offset\":%zu,"
           "\"boolean_bytes\":%zu,\"running_property\":%u,\"pcm_flags\":%u}\n",
           sizeof(AudioStreamBasicDescription), sizeof(AudioQueueBuffer),
           offsetof(AudioQueueBuffer, mAudioData), offsetof(AudioQueueBuffer, mAudioDataByteSize),
           sizeof(Boolean), (unsigned)kAudioQueueProperty_IsRunning,
           (unsigned)(kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked));
    return 0;
}
