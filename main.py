#!/usr/bin/env python3
"""
Application entrypoint for Monitoring Agent
"""

import os
import argparse
import asyncio

from hybrid_agent import create_monitoring_agent
from hybrid_agent_config import load_config_from_file

from cli.interactive import command_line_interface
from cli.batch import batch_detection_mode
from cli.single import single_image_mode


def resolve_api_key(args) -> str | None:
    if args.api_key:
        return args.api_key

    try:
        config = load_config_from_file("hybrid_agent_config.json")
        if config.openai.api_key:
            return config.openai.api_key
    except Exception:
        pass

    return os.getenv("OPENAI_API_KEY")


async def main():
    parser = argparse.ArgumentParser(description="Monitoring Agent")
    parser.add_argument("--api-key", help="OpenAI API key")
    parser.add_argument("--batch", help="Batch image directory")
    parser.add_argument("--image", help="Single image path")

    args = parser.parse_args()

    api_key = resolve_api_key(args)
    if not api_key:
        raise RuntimeError("OpenAI API key not provided")

    agent = create_monitoring_agent(api_key)

    if args.batch:
        await batch_detection_mode(agent, args.batch)
    elif args.image:
        await single_image_mode(agent, args.image)
    else:
        await command_line_interface(agent)


if __name__ == "__main__":
    asyncio.run(main())
