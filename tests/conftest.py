from __future__ import annotations

import pytest


@pytest.fixture
def sample_markdown() -> str:
    return """# Project Title

This is a brief description.

## Installation

```bash
pip install myproject
```

## Usage

Here is how to use the project.

### Basic Example

```python
from myproject import main
main.run()
```

## API Reference

### myproject.run()

The main entry point.

### myproject.configure()

Configuration function.
"""


@pytest.fixture
def sample_python_code() -> str:
    return '''"""
Module docstring.
"""

import os
from typing import Optional


def helper():
    """Helper function."""
    return True


class MyClass:
    """A sample class.

    With multi-line docstring.
    """

    def __init__(self, name: str):
        self.name = name

    def get_name(self) -> str:
        """Return the name."""
        return self.name

    async def async_method(self) -> dict:
        return {"name": self.name}


async def standalone_async():
    """Standalone async function."""
    return await some_coro()
'''


@pytest.fixture
def sample_js_code() -> str:
    return """import React from 'react';

export function Hello(props) {
    return <div>Hello {props.name}</div>;
}

export class Component {
    constructor() {
        this.state = {};
    }

    render() {
        return null;
    }
}

const arrow = () => {
    return 42;
};
"""
