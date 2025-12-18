# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import dataclasses
import os
from datetime import datetime
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from langgraph.prebuilt.chat_agent_executor import AgentState

from src.config.configuration import Configuration

# Initialize Jinja2 environment
env = Environment(
    loader=FileSystemLoader(os.path.dirname(__file__)),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True,
)

# Cache for rendered templates (without state-specific variables)
_template_cache: dict[tuple[str, str], str] = {}


def get_prompt_template(prompt_name: str, locale: str = "en-US") -> str:
    """
    Load and return a prompt template using Jinja2 with locale support.
    Uses caching to avoid repeated template file I/O.

    Args:
        prompt_name: Name of the prompt template file (without .md extension)
        locale: Language locale (e.g., en-US, zh-CN). Defaults to en-US

    Returns:
        The template string with proper variable substitution syntax
    """
    # Normalize locale format
    normalized_locale = locale.replace("-", "_") if locale and locale.strip() else "en_US"
    cache_key = (prompt_name, normalized_locale)
    
    # Check cache first
    if cache_key in _template_cache:
        return _template_cache[cache_key]
    
    try:
        # Try locale-specific template first (e.g., researcher.zh_CN.md)
        try:
            template = env.get_template(f"{prompt_name}.{normalized_locale}.md")
            result = template.render()
        except TemplateNotFound:
            # Fallback to English template if locale-specific not found
            template = env.get_template(f"{prompt_name}.md")
            result = template.render()
        
        # Cache the result
        _template_cache[cache_key] = result
        return result
    except Exception as e:
        raise ValueError(f"Error loading template {prompt_name} for locale {locale}: {e}")


def apply_prompt_template(
    prompt_name: str, state: AgentState, configurable: Configuration = None, locale: str = "en-US"
) -> list:
    """
    Apply template variables to a prompt template and return formatted messages.
    
    Optimization: Template file I/O is cached via get_prompt_template().
    Variable rendering is done once per call (cannot be cached due to dynamic state).

    Args:
        prompt_name: Name of the prompt template to use
        state: Current agent state containing variables to substitute
        configurable: Configuration object with additional variables
        locale: Language locale for template selection (e.g., en-US, zh-CN)

    Returns:
        List of messages with the system prompt as the first message
    """
    # Convert state to dict for template rendering
    state_vars = {
        "CURRENT_TIME": datetime.now().strftime("%a %b %d %Y %H:%M:%S %z"),
        **state,
    }

    # Add configurable variables
    if configurable:
        state_vars.update(dataclasses.asdict(configurable))

    try:
        # Use cached template retrieval
        template_text = get_prompt_template(prompt_name, locale)
        
        # Create Jinja2 template and render with state variables
        # Note: We create a temporary template object to preserve Jinja2 rendering behavior
        from jinja2 import Template
        template = Template(template_text)
        system_prompt = template.render(**state_vars)
        
        return [{"role": "system", "content": system_prompt}] + state["messages"]
    except Exception as e:
        raise ValueError(f"Error applying template {prompt_name} for locale {locale}: {e}")
