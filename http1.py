# https://www.rfc-editor.org/rfc/rfc1945.html
import asyncio, logging, sys, typing, enum

server_name = 'yuki0iq http/1.0 server'

@enum.unique
class Method(enum.Enum):
    GET = 1
    HEAD = 2
    POST = 3

@enum.unique
class StatusCode(enum.Enum):
    OK = 200
    Created = 201
    Accepted = 202
    NoContent = 204

    MovedPermamently = 301
    Found = 302
    NotModified = 304

    BadRequest = 400
    Unauthorized = 401
    Forbidden = 403
    NotFound = 404

    InternalServerError = 500
    NotImplemented = 501
    BadGateway = 502
    ServiceUnavailable = 503


# URI: [protocol://network_addr[:port]][/path][?query_args]
# known protocols: HTTP
# Parse(str) -> { addr: Optional[str], port: int|80, path: str, query_args: dict[str, str] }
class URI(typing.NamedTuple):
    address: typing.Optional[str] = None
    port: typing.Optional[int] = None
    path: str = '/'
    query_args: dict[str, str] = {}


# TODO undo URL-escape
def unescape(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return s


def to_uri(s: str) -> typing.Optional[URI]:
    qpos = s.index('?')
    if qpos == -1:
        qpos = len(s)
    s, args = s[:qpos], s[qpos+1:]
    s = s.lower()  # all uris are case-insensitive, lowercase use
    
    addr, port, path = None, None, s
    if '://' in s:
        if not s.startswith('http://'):
            return None
        s = s[7:]
        
        slpos = s.index('/')
        if slpos == -1:
            slpos = len(s)
        net_addr, path = s[:slpos], s[slpos:] or '/'
        
        addr, port = net_addr, 80
        scpos = net_addr.index(':')
        if scpos != -1:
            addr, maybe_port = net_addr[:scpos], net_addr[scpos+1:]
            if not maybe_port.isdigit():
                return None
            port = int(paybe_port)
            if not (0 <= port <= 65536):
                return None
    addr, path = map(unescape, (addr, path))

    query_args: dict[str, str] = {}
    for kv in args.split('&'):
        eqpos = kv.index('=')
        if eqpos == -1:
            return None
        k, v = map(unescape, (kv[:eqpos], kv[eqpos+1:]))
        query_args[k] = v

    return URI(address=addr, port=port, path=path, query_args=query_args)


# REQUEST
# Request Line:
#   Method URI [Protocol|default:HTTP/0.9]
#   Examples:
#     GET /index.html
#     -- HTTP/0.9 "GET" request to /index.html
#     POST https://example.com/index.html HTTP/1.0
#     -- HTTP/1.0 "POST" request to /index.html in https://example.com/
# Headers:
#   General:  Date, Pragma
#   Request:  Authorization, From, If-Modified-Since, Referer, User-Agent
#   Entity:   Allow, Content-Encoding, Content-Length, Content-Type, Expires, Last-Modified, <other>
def parse_request(req: str, head: list[str]) -> Request:
    # ...



def placeholder(title: str, header: str) -> str: return f"<html><head><title>{title}</title></head><body><h3>{header}</h3>{server_name}</body></html>"
async def echo_router(path: str) -> str: return placeholder("server ok", f"viewing {path}")
async def error_placeholder(err: str) -> str: return placeholder("some error", err)


async def server(host: str = '0.0.0.0', port: int = 8008) -> None:
    async def request_handler(req: str, reader: asyncio.StreamedReader) -> str:
        

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
        try:
            head = await reader.recvuntil(b'\r\n\r\n')
        except:
            # BAD HEaDER
            pass
        
        req, *headers = head.decode('utf8').replace('\r\n ', ' ').replace('\r\n\t', ' ').split('\r\n')
        # req = (await reader.readuntil()).decode('latin1').rstrip()
        logging.info(req)

        resp = await request_handler(req)
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

