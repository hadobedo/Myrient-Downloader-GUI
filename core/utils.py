"""Shared utility functions for the Myrient Downloader application."""

import os
from typing import Optional


def format_file_size(size_bytes: int) -> str:
    """Format a file size in bytes to a human-readable string.

    Args:
        size_bytes: The size in bytes to format.

    Returns:
        A human-readable string like '1.5 MB' or '3.2 GB'.
    """
    if size_bytes < 0:
        size_bytes = 0
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def generate_unique_filename(file_path: str) -> str:
    """Generate a unique filename by appending a counter suffix.

    If '/path/to/file.iso' already exists, returns '/path/to/file (1).iso', etc.

    Args:
        file_path: The original file path that conflicts.

    Returns:
        A path that does not yet exist on disk.
    """
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    name, ext = os.path.splitext(filename)

    counter = 1
    while True:
        new_filename = f"{name} ({counter}){ext}"
        new_path = os.path.join(directory, new_filename)
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def generate_unique_dirname(dir_path: str) -> str:
    """Generate a unique directory name by appending a counter suffix.

    If '/path/to/GameDir' already exists, returns '/path/to/GameDir (1)', etc.

    Args:
        dir_path: The original directory path that conflicts.

    Returns:
        A path that does not yet exist on disk.
    """
    parent_dir = os.path.dirname(dir_path)
    dir_name = os.path.basename(dir_path)

    counter = 1
    while True:
        new_dir_name = f"{dir_name} ({counter})"
        new_path = os.path.join(parent_dir, new_dir_name)
        if not os.path.exists(new_path):
            return new_path
        counter += 1
