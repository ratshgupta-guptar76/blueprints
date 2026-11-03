"""Keyword spotting for the v2 demo: spoken command words (Google Speech
Commands v2, the 12-class task) classified by a small transformer.

Division of work, as it would run on the hardware:
    chip    every multiply-accumulate (projections, attention scores and mixing,
            the feed-forward layers, the classifier), 8-bit weights and 8-bit
            activations, results exact
    FPGA    the log-mel front end, layer norm, softmax, GELU, residual adds, and
            the scaling between layers

    data.py     reads the archives, builds the train, validation and test sets
    features.py log-mel spectrogram (40 bands, 25 ms window, 10 ms hop)
    model.py    the transformer (float), and its 8-bit chip-arithmetic evaluation
    train.py    training and testing: python3 -m model.kws.train ...
    golden.py   the acceptance test: the official test set, every product bit for bit as the chip
                does it and compared with plain integer arithmetic; writes the reference answers
    pins.py     a few clips through the pin-level v2 model (model/chip_v2), about 22 minutes each
    vectors.py  one word's chip test vectors: every weight set, vector and expected result, frozen
    librispeech.py  an independent second test: the ten words cut out of LibriSpeech test-clean
"""
