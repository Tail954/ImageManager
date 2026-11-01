from dataclasses import dataclass


@dataclass(frozen=True)
class FileOperationRequest:
    operation_id: int
    operation_type: str
    source_paths: tuple[str, ...]
    destination_folder: str

    def __post_init__(self):
        object.__setattr__(self, 'source_paths', tuple(self.source_paths))


@dataclass(frozen=True)
class FileSuccess:
    source_path: str
    destination_path: str


@dataclass(frozen=True)
class FileOperationResult:
    operation_id: int
    operation_type: str
    status: str
    destination_folder: str
    successes: tuple[FileSuccess, ...]
    errors: tuple[str, ...]
