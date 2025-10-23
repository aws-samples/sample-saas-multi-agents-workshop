# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import copy
from typing import Any, AsyncGenerator
from strands import tool
from strands.types.tools import AgentTool, ToolGenerator, ToolSpec, ToolUse
import logging

logger = logging.getLogger(__name__)

class WrappedTool(AgentTool):
    def __init__(self, delegate: AgentTool) -> None:
        super().__init__()
        self._delegate = delegate

        self._bound_params = dict()

    @property
    def tool_name(self) -> str:
        return self._delegate.tool_name

    @property
    def tool_spec(self) -> ToolSpec:
        ret = copy.deepcopy(self._delegate.tool_spec)

        for name in self._bound_params.keys():
            del ret["inputSchema"]["json"]["properties"][name]

            if name in ret["inputSchema"]["json"]["required"]:
                ret["inputSchema"]["json"]["required"].remove(name)

        logger.info(f'Tool spec: {ret["inputSchema"]["json"]}')
        return ret

    @property
    def tool_type(self) -> str:
        return self._delegate.tool_type

    def bind_param(self, name: str, value: Any):
        if name in self._bound_params:
            raise ValueError(f"Parameter {name} already bound")

        tool_spec = self._delegate.tool_spec
        input_schema = tool_spec["inputSchema"]
        properties = input_schema["json"]["properties"]

        if name not in properties:
            raise ValueError(f"Can't curry {name}, becase parameter not found in tool spec")

        # TODO: Chekc for the spec and reject invalid values
        self._bound_params[name] = value

    def stream(
        self, tool_use: ToolUse, invocation_state: dict[str, Any], **kwargs
    ) -> AsyncGenerator[Any, None]:
        tool_use["input"] = {**tool_use["input"], **self._bound_params}
        logger.info(f"Tool use: {tool_use}")

        return self._delegate.stream(tool_use, invocation_state, **kwargs)
