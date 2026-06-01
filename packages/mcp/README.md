# content-kit-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes the content-kit
CLIs (`bookkit`, `podcastkit`) as tools, so an agent can drive the whole
pipeline — scaffold a book, write chapters against the canon, bridge it to an
audiobook, render audio — from plain requests.

It is a **thin adapter, generated from the CLIs themselves.** On startup it runs
`<cli> introspect` and turns every command into an MCP tool whose input schema is
derived from that command's declared arguments and typed options. Calling a tool
shells out to the CLI with `--output json` and returns the structured envelope.
There is no second source of truth: add a command or option to a CLI and it
shows up here automatically.

## Run

```bash
pip install -e ./packages/mcp        # installs the server + bookkit + podcastkit
content-kit-mcp                      # serve over stdio
```

Register it with an MCP client (e.g. Claude Desktop / Claude Code):

```json
{
  "mcpServers": {
    "content-kit": { "command": "content-kit-mcp" }
  }
}
```

Tools are named `<cli>_<command>`, e.g. `bookkit_new`, `bookkit_write_outline`,
`bookkit_audiobook`, `podcastkit_assemble`.
