import os
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def resolve_credential(
    env_var_name: str,
    cli_value: Optional[str] = None,
    provider_name: Optional[str] = None,
    signup_url: Optional[str] = None,
    auto_save_workspace_env: bool = True
) -> Optional[str]:
    """
    Unified 4-tier credential resolution hierarchy:
    1. CLI argument (if provided, optionally auto-saves to project .env)
    2. Workspace .env (./.env)
    3. Global config .env (~/.config/als-finder/.env)
    4. Environment variable / ~/.netrc

    Args:
        env_var_name (str): The environment variable name (e.g., 'OPENTOPOGRAPHY_API_KEY', 'EARTHDATA_BEARER_TOKEN').
        cli_value (Optional[str]): Value passed explicitly via CLI flag.
        provider_name (Optional[str]): Name of provider for user-friendly notifications.
        signup_url (Optional[str]): URL where user can register for free credentials.
        auto_save_workspace_env (bool): If True and cli_value is given, appends to local .env.

    Returns:
        Optional[str]: The resolved credential string, or None if not configured.
    """
    # 1. CLI Value explicitly provided
    if cli_value:
        os.environ[env_var_name] = cli_value
        if auto_save_workspace_env:
            try:
                env_path = Path.cwd() / ".env"
                with open(env_path, "a", encoding="utf-8") as f:
                    f.write(f"\n{env_var_name}={cli_value}\n")
                logger.info(f"Credential '{env_var_name}' saved to {env_path}")
            except Exception as e:
                logger.warning(f"Could not auto-save {env_var_name} to .env: {e}")
        return cli_value

    # 2. Local workspace .env
    workspace_env = Path.cwd() / ".env"
    if workspace_env.exists():
        load_dotenv(workspace_env)
        val = os.getenv(env_var_name)
        if val:
            return val

    # 3. Global config .env
    global_env = Path.home() / ".config" / "als-finder" / ".env"
    if global_env.exists():
        load_dotenv(global_env)
        val = os.getenv(env_var_name)
        if val:
            return val

    # 4. Existing environment variable
    val = os.getenv(env_var_name)
    if val:
        return val

    # Pre-flight notification banner if missing
    if provider_name and signup_url:
        logger.warning(
            f"\n{'='*78}\n"
            f"[!] Authentication Notice for {provider_name}\n"
            f"{'-'*78}\n"
            f"No credential found for '{env_var_name}'.\n"
            f"To access {provider_name} datasets, register for a free key/token at:\n"
            f"  -> {signup_url}\n"
            f"Then pass it via CLI once to auto-cache in your workspace:\n"
            f"  als-finder search --roi <file> --{env_var_name.lower().replace('_', '-')}=<YOUR_TOKEN>\n"
            f"{'='*78}\n"
        )

    return None
