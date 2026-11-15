These two unmodified pixel crops come from the real Linux MainKt smoke failure on game JAR 88283267eefaf417da4965a1248c1b70b9188effd71f6ee3f69cc2c1911e5bc1. The first fox is visible at 65% opacity during startup protection; the second is opaque. The detector must wait for identifiable opaque frames, and must never index a missing detection.

```json
{
  "released-translucent.png": {
    "original": "build/audio-linux-private-smoke/source/movement-released.png",
    "original_sha256": "db3c225e7ae60c899f1de7144575cfe674a9d19ebf1f5c4192139bc6fb133b31",
    "crop": [
      180,
      480,
      260,
      540
    ]
  },
  "rested-opaque.png": {
    "original": "build/audio-linux-private-smoke/source/movement-rested.png",
    "original_sha256": "626e41ffcf7bcf7ca5b536880dd0116bb1a44ba44e88f97df2144cb72ac67bf9",
    "crop": [
      180,
      480,
      260,
      540
    ]
  }
}
```
