import os


def draw_tree(path, prefix="", ignore=None):
    """Recursively print directory tree structure, ignoring given folders."""
    if ignore is None:
        ignore = []

    items = sorted(os.listdir(path))
    # Filter out ignored directories
    items = [item for item in items if item not in ignore]

    for i, item in enumerate(items):
        item_path = os.path.join(path, item)
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "
        print(prefix + connector + item)
        if os.path.isdir(item_path):
            extension = "    " if is_last else "│   "
            draw_tree(item_path, prefix + extension, ignore=ignore)


if __name__ == "__main__":
    directory = input("Enter directory path: ").strip()
    ignore_input = input("Enter folders to ignore (comma-separated, e.g. .git,.idea): ").strip()
    ignore_folders = [f.strip() for f in ignore_input.split(",")] if ignore_input else []

    if not os.path.exists(directory):
        print("Directory does not exist.")
    else:
        print(directory)
        draw_tree(directory, ignore=ignore_folders)
