"""
Test Session Manager - Manages deterministic test sessions for replication

Allows saving test input batches as named sessions and replaying them exactly.
Each session stores:
- Input SVG batch (the exact frames used)
- uv.lock file (dependency versions)
- Metadata (timestamp, config, frame count, etc.)

Why:
    Enable regression testing and performance comparison across test runs
"""

import json
import shutil
from datetime import datetime
from pathlib import Path


class TestSession:
    """
    Represents a single test session with its inputs and metadata
    """

    def __init__(
        self,
        session_id: str,
        frame_count: int,
        timestamp: str,
        input_batch_dir: Path,
        uv_lock_path: Path | None = None,
        metadata: dict | None = None,
    ):
        self.session_id = session_id
        self.frame_count = frame_count
        self.timestamp = timestamp
        self.input_batch_dir = input_batch_dir
        self.uv_lock_path = uv_lock_path
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        """Convert session to dictionary for JSON storage"""
        return {
            "session_id": self.session_id,
            "frame_count": self.frame_count,
            "timestamp": self.timestamp,
            "input_batch_dir": str(self.input_batch_dir),
            "uv_lock_path": str(self.uv_lock_path) if self.uv_lock_path else None,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: dict, base_dir: Path) -> "TestSession":
        """Create session from dictionary"""
        return TestSession(
            session_id=data["session_id"],
            frame_count=data["frame_count"],
            timestamp=data["timestamp"],
            input_batch_dir=Path(data["input_batch_dir"]),
            uv_lock_path=Path(data["uv_lock_path"]) if data.get("uv_lock_path") else None,
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """
    Manages test sessions for deterministic test replication

    Directory structure:
        tests/sessions/
            index.json              # Registry of all sessions
            session_001/
                input_batch/        # Input SVG files
                uv.lock             # Dependency lock file
                metadata.json       # Session metadata
            session_002/
                ...
    """

    def __init__(self, sessions_root: Path):
        """
        Initialize session manager

        Args:
            sessions_root: Root directory for session storage (tests/sessions/)
        """
        self.sessions_root = sessions_root
        self.index_file = sessions_root / "index.json"
        self.sessions_root.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> dict[str, dict]:
        """Load session index from disk"""
        if not self.index_file.exists():
            return {}

        with open(self.index_file) as f:
            return json.load(f)

    def _save_index(self, index: dict[str, dict]):
        """Save session index to disk"""
        with open(self.index_file, "w") as f:
            json.dump(index, f, indent=2)

    def _generate_session_id(self, frame_count: int) -> str:
        """
        Generate next available session ID

        Format: session_<NNN>_<frame_count>frames
        Example: session_001_3frames, session_002_10frames
        """
        index = self._load_index()

        # Find highest session number
        max_num = 0
        for session_id in index.keys():
            if session_id.startswith("session_"):
                try:
                    num = int(session_id.split("_")[1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    continue

        next_num = max_num + 1
        return f"session_{next_num:03d}_{frame_count}frames"

    def save_session(
        self,
        frame_count: int,
        input_batch_dir: Path,
        test_config: dict,
        svg_sources: list[Path],
        session_id: str | None = None,
    ) -> TestSession:
        """
        Save a test session for future replication

        Args:
            frame_count: Number of frames in batch
            input_batch_dir: Path to input batch directory to preserve
            test_config: Test configuration (FPS, resolution, etc.)
            svg_sources: List of original SVG source paths
            session_id: Optional custom session ID (auto-generated if None)

        Returns:
            TestSession object with session details

        Why:
            Preserve exact test conditions for regression testing
        """
        # Generate or validate session ID
        if session_id is None:
            session_id = self._generate_session_id(frame_count)
        else:
            # Check if session already exists
            index = self._load_index()
            if session_id in index:
                raise ValueError(f"Session '{session_id}' already exists")

        # Create session directory
        session_dir = self.sessions_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Copy input batch
        session_batch_dir = session_dir / "input_batch"
        if session_batch_dir.exists():
            shutil.rmtree(session_batch_dir)
        shutil.copytree(input_batch_dir, session_batch_dir)

        # Copy uv.lock from project root
        project_root = self.sessions_root.parent.parent  # tests/sessions/ -> tests/ -> project_root/
        uv_lock_source = project_root / "uv.lock"
        uv_lock_dest = None

        if uv_lock_source.exists():
            uv_lock_dest = session_dir / "uv.lock"
            shutil.copy2(uv_lock_source, uv_lock_dest)

        # Create metadata
        timestamp = datetime.now().isoformat()
        metadata = {
            "session_id": session_id,
            "frame_count": frame_count,
            "timestamp": timestamp,
            "test_config": test_config,
            "svg_sources": [str(p) for p in svg_sources],
            "created_by": "test_frame_rendering",
            "description": f"{frame_count}-frame test session",
        }

        # Save metadata
        metadata_file = session_dir / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        # Create session object
        session = TestSession(
            session_id=session_id,
            frame_count=frame_count,
            timestamp=timestamp,
            input_batch_dir=session_batch_dir,
            uv_lock_path=uv_lock_dest,
            metadata=metadata,
        )

        # Update index
        index = self._load_index()
        index[session_id] = session.to_dict()
        self._save_index(index)

        print(f"✓ Session saved: {session_id}")
        print(f"  Location: {session_dir}")
        print(f"  Frames: {frame_count}")

        return session

    def load_session(self, session_id: str) -> TestSession | None:
        """
        Load a saved test session

        Args:
            session_id: Session ID to load

        Returns:
            TestSession object or None if not found

        Why:
            Retrieve exact test conditions for replication
        """
        index = self._load_index()

        if session_id not in index:
            return None

        session_data = index[session_id]
        return TestSession.from_dict(session_data, self.sessions_root)

    def list_sessions(self) -> list[TestSession]:
        """
        List all available sessions

        Returns:
            List of TestSession objects, sorted by session ID

        Why:
            Show available sessions for selection
        """
        index = self._load_index()
        sessions = []

        for session_id in sorted(index.keys()):
            session = TestSession.from_dict(index[session_id], self.sessions_root)
            sessions.append(session)

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a saved session

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted, False if not found

        Why:
            Clean up old or invalid sessions
        """
        index = self._load_index()

        if session_id not in index:
            return False

        # Remove session directory
        session_dir = self.sessions_root / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

        # Remove from index
        del index[session_id]
        self._save_index(index)

        print(f"✓ Session deleted: {session_id}")
        return True

    def get_session_info(self, session_id: str) -> dict | None:
        """
        Get detailed information about a session

        Args:
            session_id: Session ID

        Returns:
            Session metadata dictionary or None if not found
        """
        session = self.load_session(session_id)
        if not session:
            return None

        # Load full metadata from session directory
        metadata_file = self.sessions_root / session_id / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file) as f:
                return json.load(f)

        return session.metadata
