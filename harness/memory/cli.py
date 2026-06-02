#!/usr/bin/env python3
"""
Memory Management CLI

Provides CLI commands for memory management.

Usage:
  python memory/cli.py list      # List all memory entries
  python memory/cli.py clear     # Clear session memory
  python memory/cli.py read      # Read memory
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from harness.memory.memory_manager import MemoryManager, MemoryEntry


def list_memory():
    """List all memory entries in session buffer."""
    mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")
    entries = mm.get_session_memory()

    if not entries:
        print("No memory entries yet.")
        return

    print()
    print("=" * 60)
    print("  SESSION MEMORY")
    print("=" * 60)
    print()

    for i, entry in enumerate(entries, 1):
        print(f"[{i}] {entry.name}")
        print(f"    Description: {entry.description}")
        if len(entry.content) > 200:
            print(f"    Content: {entry.content[:200]}...")
        else:
            print(f"    Content: {entry.content}")
        print()

    print("=" * 60)


def clear_memory():
    """Clear session memory."""
    mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")
    mm.clear_session()
    print("Session memory cleared.")


def read_memory():
    """Read and display memory entries."""
    mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")
    entries = mm.get_session_memory()

    if not entries:
        print("No memory entries to read.")
        return

    for entry in entries:
        if entry.content:
            print()
            print(f"## {entry.name}")
            print(entry.content)
            print("-" * 60)


def add_memory(name: str, description: str, content: str, category: str = "project"):
    """Add a new memory entry."""
    mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")

    entry = MemoryEntry(
        name=name,
        description=description,
        content=content,
        category=category
    )

    mm.append_to_now(entry)
    mm.save_entry(entry, category)

    print(f"Added memory entry: {name}")
    print(f"  Description: {description}")
    print(f"  Category: {category}")


def save_reference(name: str, url: str, description: str = ""):
    """Save a reference (documentation URL) to memory."""
    mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")
    mm.save_reference(name, url, description)
    print(f"Saved reference: {name} -> {url}")


def save_feedback(name: str, content: str, why: str = "", how: str = ""):
    """Save feedback to memory."""
    mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")
    mm.save_feedback(name, content, why, how)
    print(f"Saved feedback: {name}")


def save_project(name: str, content: str):
    """Save project information to memory."""
    mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")
    mm.save_project(name, content)
    print(f"Saved project info: {name}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="harness-memory",
        description="Harness Memory Management CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    subparsers.add_parser("list", help="List memory entries")

    # Clear command
    subparsers.add_parser("clear", help="Clear session memory")

    # Read command
    subparsers.add_parser("read", help="Read memory entries")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add memory entry")
    add_parser.add_argument("name", help="Entry name")
    add_parser.add_argument("description", help="Entry description")
    add_parser.add_argument("content", help="Entry content")
    add_parser.add_argument("--category", "-c", default="project",
                           choices=["user", "feedback", "project", "reference"],
                           help="Entry category")

    # Reference command
    ref_parser = subparsers.add_parser("reference", help="Save reference")
    ref_parser.add_argument("name", help="Reference name")
    ref_parser.add_argument("url", help="URL")
    ref_parser.add_argument("--description", "-d", default="",
                           help="Description")

    # Feedback command
    feedback_parser = subparsers.add_parser("feedback", help="Save feedback")
    feedback_parser.add_argument("name", help="Feedback name")
    feedback_parser.add_argument("content", help="Feedback content")
    feedback_parser.add_argument("--why", "-w", default="",
                               help="Why this feedback matters")
    feedback_parser.add_argument("--how", "-h", default="",
                               help="How to apply this feedback")

    # Project command
    subparsers.add_parser("project", help="Save project info")

    # Status command
    subparsers.add_parser("status", help="Show memory status")

    args = parser.parse_args()

    if args.command == "list":
        list_memory()

    elif args.command == "clear":
        clear_memory()

    elif args.command == "read":
        read_memory()

    elif args.command == "add":
        add_memory(
            name=args.name,
            description=args.description,
            content=args.content,
            category=args.category
        )

    elif args.command == "reference":
        save_reference(
            name=args.name,
            url=args.url,
            description=args.description
        )

    elif args.command == "feedback":
        save_feedback(
            name=args.name,
            content=args.content,
            why=args.why,
            how=args.how
        )

    elif args.command == "project":
        save_project(args.name, args.content)

    elif args.command == "status":
        mm = MemoryManager(Path(__file__).parent.parent.parent / ".remember")
        entries = mm.get_session_memory()
        print(f"Memory entries: {len(entries)}")
        print("Categories:")
        print("  - user        : User preferences and identity")
        print("  - feedback    : How to behave and learnings")
        print("  - project     : Project information")
        print("  - reference   : Documentation URLs")


if __name__ == "__main__":
    main()
