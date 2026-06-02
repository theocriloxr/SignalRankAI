"""
core/patch_manager.py - Safe Patch Application System

This module handles the application of Gemini-generated patches with automatic backup.
It ensures that AI-generated changes are applied safely with rollback capability.

Usage:
    pm = PatchManager()
    success, backup_path = await pm.apply_gemini_patch("engine/stale_validator.py", patch_content)
"""
import os
import shutil
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger("patch_manager")


class PatchManager:
    def __init__(self, repo_path: str = "./"):
        self.repo_path = Path(repo_path)
        self.backup_dir = self.repo_path / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, file_path: str) -> Path:
        """Saves a copy of the file before editing."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = Path(file_path).name
        backup_path = self.backup_dir / f"{filename}.{timestamp}.bak"
        shutil.copy2(file_path, backup_path)
        logger.info(f"[patch_manager] Backup created: {backup_path}")
        return backup_path

    def list_backups(self, filename: Optional[str] = None) -> list[Path]:
        """List available backups, optionally filtered by original filename."""
        if filename:
            pattern = f"{Path(filename).name}.*.bak"
        else:
            pattern = "*.bak"
        return sorted(self.backup_dir.glob(pattern), reverse=True)

    def restore_backup(self, backup_path: Path, target_file: str) -> bool:
        """Restore a file from backup."""
        try:
            shutil.copy2(backup_path, target_file)
            logger.info(f"[patch_manager] Restored: {target_file} from {backup_path}")
            return True
        except Exception as e:
            logger.error(f"[patch_manager] Restore failed: {e}")
            return False

    async def apply_gemini_patch(self, target_file: str, patch_content: str) -> Tuple[bool, Optional[Path]]:
        """
        Applies a unified diff patch to a target file.
        
        Args:
            target_file: Path to the file to patch
            patch_content: The unified diff content
            
        Returns:
            (success: bool, backup_path: Optional[Path])
        """
        target_path = self.repo_path / target_file
        if not target_path.exists():
            logger.error(f"[patch_manager] Target file not found: {target_file}")
            return False, None

        try:
            # 1. Backup the original
            backup = self.create_backup(str(target_path))
            
            # 2. Write patch to temp file
            patch_file = self.repo_path / "temp_upgrade.patch"
            with open(patch_file, "w", encoding="utf-8") as f:
                f.write(patch_content)
            
            # 3. Apply the patch using 'git apply' or 'patch'
            # First check if it's clean
            check = subprocess.run(
                ["git", "apply", "--check", str(patch_file)],
                capture_output=True,
                cwd=self.repo_path
            )
            
            if check.returncode == 0:
                # Apply the patch
                subprocess.run(
                    ["git", "apply", str(patch_file)],
                    capture_output=True,
                    cwd=self.repo_path
                )
                # Clean up temp patch file
                patch_file.unlink(missing_ok=True)
                logger.info(f"[patch_manager] ✅ Successfully patched {target_file}. Backup: {backup}")
                return True, backup
            else:
                # Patch check failed - try manual apply
                logger.warning(f"[patch_manager] Git apply check failed, trying manual apply")
                patch_file.unlink(missing_ok=True)
                return False, None
                
        except Exception as e:
            logger.error(f"[patch_manager] System Error applying patch: {e}")
            return False, None

    async def apply_inline_patch(self, target_file: str, new_content: str) -> Tuple[bool, Optional[Path]]:
        """
        Apply a patch by replacing entire file content (for simple changes).
        
        Args:
            target_file: Path to the file to patch
            new_content: The new file content
            
        Returns:
            (success: bool, backup_path: Optional[Path])
        """
        target_path = self.repo_path / target_file
        if not target_path.exists():
            logger.error(f"[patch_manager] Target file not found: {target_file}")
            return False, None

        try:
            # 1. Backup the original
            backup = self.create_backup(str(target_path))
            
            # 2. Write new content
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            logger.info(f"[patch_manager] ✅ Successfully updated {target_file}. Backup: {backup}")
            return True, backup
            
        except Exception as e:
            logger.error(f"[patch_manager] System Error applying patch: {e}")
            return False, None


# Global instance for easy importing
patch_manager = PatchManager()
