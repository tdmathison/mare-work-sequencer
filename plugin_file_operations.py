"""Bounded virtual package operations. Never resolve or mutate host filesystem paths."""
import re
from pathlib import PurePosixPath
import plugin_store as store


def destination_path(path):
    result = store.safe_path(path)
    if re.search(r'[<>"|?*]', result) or any(part.endswith((' ', '.')) for part in result.split('/')):
        raise ValueError('Names cannot contain <>"|?* or end in a space or period.')
    return result


def directory_exists(entries, path):
    return path == '' or bool(entries.get(path, {}).get('directory')) or any(p.startswith(path + '/') for p in entries)


def organize(entries, operation, paths, destination='', target=None):
    if not isinstance(paths, list) or not paths or len(paths) > store.MAX_FILES:
        raise ValueError('Select one or more package items.')
    sources = sorted(set(store.safe_path(path) for path in paths), key=lambda p: (p.count('/'), p))
    roots = []
    for path in sources:
        if path not in entries and not directory_exists(entries, path):
            raise FileNotFoundError('The source no longer exists: ' + path)
        if not any(path.startswith(parent + '/') for parent in roots):
            roots.append(path)
    if operation != 'copy' and 'plugin.json' in roots:
        raise ValueError('The root plugin.json manifest cannot be moved, renamed or deleted. Its contents remain editable.')
    removed = {p for p in entries if any(p == source or p.startswith(source + '/') for source in roots)}
    if operation == 'delete':
        result = {p: value for p, value in entries.items() if p not in removed}
        return result, {'roots': [], 'deleted': roots}
    if operation not in ('move', 'copy', 'rename'):
        raise ValueError('Unsupported organization operation.')
    if operation == 'rename':
        if len(roots) != 1:
            raise ValueError('Rename one item at a time.')
        targets = [destination_path(target)]
        parent = targets[0].rpartition('/')[0]
        if not directory_exists(entries, parent):
            raise ValueError('The destination folder does not exist.')
    else:
        if not isinstance(destination, str):
            raise ValueError('The destination must be a package-relative folder path.')
        destination = destination_path(destination) if destination else ''
        if not directory_exists(entries, destination):
            raise ValueError('The destination must be an existing package folder.')
        targets = [destination_path((destination + '/' if destination else '') + path.rsplit('/', 1)[-1]) for path in roots]
    retained = dict(entries) if operation == 'copy' else {p: v for p, v in entries.items() if p not in removed}
    occupied = set(p.casefold() for p in entries)
    # Include implicit parent folders so merging into one never silently overwrites it.
    for path in entries:
        occupied.update('/'.join(path.split('/')[:i]).casefold() for i in range(1, len(path.split('/'))))
    mapping = []
    for source, initial in zip(roots, targets):
        candidate = initial
        if candidate.casefold().startswith(source.casefold() + '/'):
            raise ValueError('A folder cannot be placed inside itself or a descendant.')
        if operation == 'copy' and candidate.casefold() in occupied:
            parent, _, name = candidate.rpartition('/')
            extension = '' if directory_exists(entries, source) or name.startswith('.') else PurePosixPath(name).suffix
            stem = name[:-len(extension)] if extension else name
            for index in range(1, 201):
                name = stem + (' copy' if index == 1 else ' copy ' + str(index)) + extension
                candidate = destination_path((parent + '/' if parent else '') + name)
                if candidate.casefold() not in occupied:
                    break
            else:
                raise ValueError('No unused copy name is available.')
        elif candidate == source:
            raise ValueError('That item is already in the destination folder.')
        elif candidate.casefold() in occupied and candidate.casefold() != source.casefold():
            raise ValueError('The destination already exists: ' + candidate)
        subtree = {candidate + p[len(source):]: v for p, v in entries.items() if p == source or p.startswith(source + '/')}
        for path in subtree:
            destination_path(path)
            if any(path.casefold() == existing.casefold() for existing in retained):
                raise ValueError('The destination already exists: ' + path)
        retained.update(subtree)
        occupied.update(p.casefold() for p in subtree)
        mapping.append({'source': source, 'target': candidate})
    store.validate_tree(retained)
    return retained, {'roots': mapping, 'deleted': []}
