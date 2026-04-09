from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train CPU classifier from labeled samples.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--task", choices=["floor", "direction"], required=True)
    parser.add_argument("--epochs", type=int, default=18)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--image-size", type=int, default=96)
    return parser.parse_args()


def load_rows(data_dir: Path, task: str) -> list[tuple[Path, str]]:
    db_path = data_dir / "labels.db"
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT image_path, confirmed_label
            FROM labels
            WHERE kind = ?
            ORDER BY created_at
            """,
            (task,),
        ).fetchall()
    return [(Path(path), str(label)) for path, label in rows if Path(path).exists()]


def load_image(path: Path, image_size: int) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"Failed to load image: {path}")
    resized = cv2.resize(image, (image_size, image_size), interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32) / 255.0


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    rows = load_rows(data_dir, args.task)
    if not rows:
        raise SystemExit(f"No labeled samples found for task={args.task!r} in {data_dir}")

    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise SystemExit("Torch is required for training. Install with `pip install -e '.[train]'`.") from exc

    from app.ml_model import SmallClassifier

    labels = sorted({label for _, label in rows})
    label_to_index = {label: idx for idx, label in enumerate(labels)}

    images = np.stack([load_image(path, args.image_size) for path, _ in rows])
    targets = np.array([label_to_index[label] for _, label in rows], dtype=np.int64)

    tensor_x = torch.from_numpy(images[:, np.newaxis, :, :])
    tensor_y = torch.from_numpy(targets)
    dataset = TensorDataset(tensor_x, tensor_y)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)

    model = SmallClassifier(num_classes=len(labels))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(args.epochs):
        running_loss = 0.0
        correct = 0
        total = 0
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()

            running_loss += float(loss.item()) * batch_x.size(0)
            predictions = logits.argmax(dim=1)
            correct += int((predictions == batch_y).sum().item())
            total += int(batch_x.size(0))

        epoch_loss = running_loss / max(1, total)
        epoch_acc = correct / max(1, total)
        print(f"epoch={epoch + 1} loss={epoch_loss:.4f} acc={epoch_acc:.4f}")

    model_dir = data_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_dir / f"{args.task}_model.pt")
    metadata = {
        "task": args.task,
        "labels": labels,
        "image_width": args.image_size,
        "image_height": args.image_size,
        "num_samples": len(rows),
        "last_accuracy": epoch_acc,
    }
    (model_dir / f"{args.task}_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"saved model to {model_dir / f'{args.task}_model.pt'}")


if __name__ == "__main__":
    main()
