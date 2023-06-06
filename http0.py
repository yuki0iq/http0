# https://www.w3.org/Protocols/HTTP/AsImplemented.html
import asyncio, logging, sys, typing


RouterType = typing.Callable[[str], typing.Awaitable[str]]
server_name = 'simple http/0.9 server'

def placeholder(title: str, header: str) -> str: return f"<html><head><title>{title}</title></head><body><h3>{header}</h3>{server_name}</body></html>"
async def echo_router(path: str) -> str: return placeholder("server ok", f"viewing {path}")
async def error_placeholder(err: str) -> str: return placeholder("some error", err)


async def server(host: str = '0.0.0.0', port: int = 8008, router: RouterType = echo_router, error_reporter: RouterType = error_placeholder) -> None:
    async def server_impl(req: str) -> str:
        space = req.index(' ')
        if space == -1:
            return await error_reporter("Bad request: no path")
        method, rest = req[:space], req[space+1:]
        second_space = rest.index(' ')
        path = rest if second_space == -1 else rest[:second_space]
        logging.debug(f"method {method} path {path}")
        if method != 'GET':
            return await error_reporter("Unsupported method")
        return await router(path)

    async def server_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        req = (await reader.readuntil()).decode('latin1').rstrip()
        logging.info(req)

        resp = await server_impl(req)
        logging.debug(f"Response: {resp}")
        writer.write(resp.encode())
        await writer.drain()

        logging.debug("Connection close")
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(server_handler, host, port)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    logging.info(f'{server_name} is serving on {addrs} with port {port}')

    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    logging.basicConfig(level=(logging.DEBUG if 'debug' in sys.argv else logging.INFO))
    asyncio.get_event_loop().run_until_complete(server('0.0.0.0', 8008))

