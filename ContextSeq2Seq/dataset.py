import json
from pathlib import Path
from typing import Iterator, NamedTuple

import numpy as np
import torch
from torch.utils.data import Dataset
from torch.nn.utils.rnn import pad_sequence

from text import Vocab, parse_transcripts, TokenContainer, pad_matrix

AVERAGE_POSE = np.array(
    [
        -4.87763543e-03,
        -3.28306228e-03,
        -3.52207881e-02,
        2.91140693e-01,
        -1.30582738e00,
        -2.67789574e-01,
        4.93647768e-01,
        2.97261734e-02,
        -1.03489816e00,
        -1.12113014e-02,
        2.60010556e-01,
        -1.77651438e-02,
        1.04002508e-03,
        -8.69302131e-02,
        7.29609870e-03,
        2.77519515e-01,
        1.19936582e00,
        2.08790903e-01,
        3.82341444e-01,
        6.83493300e-02,
        1.01232966e00,
        -2.05920467e-02,
        -2.67993718e-01,
        4.26632091e-02,
        -3.06026048e-01,
        -6.61230600e-03,
        -6.86834346e-03,
        -4.11315190e-02,
        -7.51190893e-02,
        -1.41461157e-02,
        1.89925843e-01,
        -7.22872507e-03,
        -4.27592980e-03,
        3.45107884e-02,
        -2.24161020e-02,
        3.37464364e-02,
        8.40320133e-03,
        -1.86894631e-02,
        -2.31109196e-02,
        8.54747952e-02,
        9.69810320e-03,
        -2.45954971e-02,
        2.53486126e-02,
        -3.35889872e-03,
        -8.27389301e-02,
    ]
)

AVERAGE_POSE = AVERAGE_POSE[None, :]
# AVERAGE_POSE - 1, output_dim


class Seq2SeqDataset(Dataset):
    def __init__(
        self,
        data_files: Iterator[str],
        previous_poses: int = 10,
        predicted_poses: int = 20,
        stride: int = 20,
        with_context: bool = False,
        text_folder: str = None,
        vocab: Vocab = None
    ):
        self.previous_poses = previous_poses
        self.predicted_poses = predicted_poses
        self.features = []
        self.poses = []
        self.prev_poses = []
        self.words = None
        if vocab:
            self.words = []

        if text_folder:
            text_folder = Path(text_folder)

        for file in data_files:
            data = np.load(file)
            if str(file).endswith('npy'):
                X = data
                Y = None
            else:
                X = data["X"]
                Y = data["Y"]
            n = X.shape[0]

            token_container = None  # type: TokenContainer
            if text_folder is not None:
                filename = file.name.split(".")[0]
                filenumber = filename[-3:]
                text_file = text_folder / f"Recording_{filenumber}.json"
                token_container = parse_transcripts(text_file, vocab)

            assert Y is None or X.shape[0] == Y.shape[0]
            # x - N, 61, 26
            # todo: add + 1 for inference
            strides = (n - predicted_poses + stride) // stride
            for i in range(strides):
                # we have features and poses from i...i + predicted_poses
                # we have previous poses from i + predicted_poses - previous_states ... i + predicted_staes
                if token_container:
                    w = token_container[i * stride: i * stride + predicted_poses]  # [predicted_poses, words_count*]
                    self.words.append(w)
                if with_context:
                    x = X[i * stride: i * stride + predicted_poses]
                else:
                    x = X[i * stride: i * stride + predicted_poses, 30]
                y = Y[i * stride: i * stride + predicted_poses] if Y is not None else None
                p = Y[i * stride - previous_poses: i * stride] if Y is not None else None
                if  p is None or len(p) == 0:
                    p = AVERAGE_POSE.repeat(self.previous_poses, 0)
                if y is None:
                    y = AVERAGE_POSE.repeat(self.predicted_poses, 0)
                self.features.append(x)
                self.poses.append(y)
                self.prev_poses.append(p)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, index: int):
        x = torch.FloatTensor(self.features[index])
        y = torch.FloatTensor(self.poses[index])
        p = torch.FloatTensor(self.prev_poses[index])

        if self.words:
            w = self.words[index]  # list(seq_len, words_count)
            w = [torch.LongTensor(frame) if len(frame) > 0 else torch.LongTensor([0]) for frame in w]
            w = pad_sequence(w, batch_first=True)
            return x, y, p, w
        return x, y, p

    @staticmethod
    def collate_fn(batch):
        if len(batch[0]) == 4:
            x, y, p, w = list(zip(*batch))
            X = torch.stack(x, dim=1)
            Y = torch.stack(y, dim=1)
            P = torch.stack(p, dim=1)
            W = pad_matrix(w) # batch_size, seq_len, words_count
            W = W.transpose(0, 1) # seq_len, batch_size, words_count
            return X, Y, P, W

        x, y, p = list(zip(*batch))
        X = torch.stack(x, dim=1)
        Y = torch.stack(y, dim=1)
        P = torch.stack(p, dim=1)
        return X, Y, P
