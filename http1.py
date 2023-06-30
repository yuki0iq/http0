# https://www.rfc-editor.org/rfc/rfc1945.html
import typing, enum
import logging, sys, platform
import asyncio
import datetime

server_name = f'YukiHTTP/1.0 ({platform.python_implementation()}/{platform.python_version()})'


# TODO: POST, additional methods?
# TODO: More convenient headers editor?
# TODO: Additional headers support
# TODO: proper CRLF handle in response headers (should never occur, 500?)
# TODO: unescape of URL query's kv (and reverse...)
# TODO: more clear interface for 3xx[Redirect]. What if every status will be a class?
# TODO: HEAD, If-Modified-Since


@enum.unique
class Method(enum.Enum):
    GET = 1
    HEAD = 2
    POST = 3

    def __str__(self) -> str:
        return self.name


@enum.unique
class Status(enum.Enum):
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

    def __str__(self) -> str:
        return self.name


# URI: [protocol://network_addr[:port]][/path][?query_args]
# known protocols: HTTP
# Parse(str) -> { addr: Optional[str], port: int|80, path: str, query_args: dict[str, str] }
class URI(typing.NamedTuple):
    path: str = '/'
    query_args: dict[str, str] = {}


# TODO undo URL-escape
def unescape(s: bytes) -> bytes:
    return s


def to_key_value(args: bytes, argsep: bytes = b'\r\n', kvsep: bytes = b':', escaped: bool = False, lstrip: bool = True) -> dict[str, str]:
    res: dict[str, str] = {}
    if args:
        for kv in args.split(argsep):
            pos = kv.find(kvsep)
            if pos == -1:
                continue
            k, v = kv[:pos], kv[pos+1:]
            if lstrip:
                v = v.lstrip()
            if escaped:
                k, v = unescape(k), unescape(v)
            ks, vs = k.decode('utf8'), v.decode('utf8')
            res[ks] = vs
    return res


def to_path(s: bytes) -> URI:
    qpos = s.find(b'?')
    if qpos == -1:
        qpos = len(s)
    path, args = s[:qpos], s[qpos+1:]

    path_s = unescape(path).decode('utf8')
    query_args = to_key_value(args, b'&', b'=', escaped=True, lstrip=False) 
    return URI(path=path_s, query_args=query_args)


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
#   Response: Location, Server, WWW-Authenticate
#   Entity:   Allow, Content-Encoding, Content-Length, Content-Type, Expires, Last-Modified, <other>
class Request(typing.NamedTuple):
    method: Method
    path: URI
    proto: str
    headers: dict[str, str] = {}
    reader: typing.Optional[asyncio.StreamReader] = None


class Response(typing.NamedTuple):
    proto: str
    code: Status
    code_str: typing.Optional[str]
    headers: dict[str, typing.Any]
    body: typing.Any  # TODO


def date_to_str(dt: datetime.datetime) -> str:
    # RFC1123
    weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dt.weekday()]
    month = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][dt.month]
    return f"{weekday}, {dt.day:02} {month} {dt.year} {dt.hour:02}:{dt.minute:02}:{dt.second:02} GMT"


def make_response(proto: str, code: Status, expl: typing.Optional[str], head: dict[str, typing.Any], body: typing.Any) -> Response:
    return Response(proto, code, expl, head | { 'Date': date_to_str(datetime.datetime.utcnow()), 'Server': server_name }, body)


def make_html(proto: str, code: Status, expl: typing.Optional[str], head: dict[str, typing.Any], body: typing.Any) -> Response:
    body_enc = body.encode('utf8')
    return make_response(proto, code, expl, head | { 'Content-Type': 'text/html', 'Content-Length': len(body_enc) }, body_enc)


def error(code: Status, expl: typing.Optional[str] = None, proto: str = 'HTTP/1.0') -> Response:
    title = f"{code.value} {code}"
    stub = f"<html><head><title>{title}</title></head><body style='text-align: center'> <h1>{title}</h1> {expl or ''} <hr> <i>{server_name}</i> </body></html>"
    return make_html(proto, code, expl, dict(), stub)


async def parse_request(reader: asyncio.StreamReader) -> typing.Union[Request, Response]:
    try:
        req = await reader.readuntil(b'\r\n')
        meth, uri, *ver = req[:-2].split()
        method = Method[meth.decode('utf8').upper()]
        path = to_path(uri)
        if len(ver) > 1:
            return error(Status.BadRequest, 'Wrong request line format: too much arguments')
        proto = ver[0].decode('utf8').upper() if ver else 'HTTP/0.9'
        if not proto.startswith('HTTP/'):
            return error(Status.BadRequest, 'Unknown protocol')
        if proto == 'HTTP/0.9':
            if method != Method.GET:
                return error(Status.BadRequest, 'Protocol unsupported method')
            if not path.path.startswith('/'):
                return error(Status.BadRequest, 'HTTP/0.9 does not support full paths')
            return Request(method, path, proto)
    except asyncio.LimitOverrunError:
        return error(Status.BadRequest, 'Request line too long')
    except asyncio.IncompleteReadError:
        return error(Status.BadRequest, 'Connection break')
    except UnicodeError:
        return error(Status.BadRequest, 'UTF-8 decode error in request line')
    except ValueError:
        return error(Status.BadRequest, 'Wrong request line format: not enough arguments')
    except KeyError:
        return error(Status.BadRequest, 'Server unsupported method')

    try:
        head = await reader.readuntil(b'\r\n\r\n')
        fixed_head = head[:-4].replace(b'\r\n ', b' ').replace(b'\r\n\t', b' ')
        headers = to_key_value(fixed_head)
    except asyncio.LimitOverrunError:
        return error(Status.BadRequest, 'Headers too long')
    except asyncio.IncompleteReadError:
        return error(Status.BadRequest, 'Connection break')
    except UnicodeError:
        return error(Status.BadRequest, 'UTF-8 decode error in headers')

    return Request(method, path, proto, headers, reader)


async def request_handler(req: Request) -> Response:
    res = ''.join([
        f"<html><head><title>{req.path}</title></head><body><table>",
        "<tr><th>Key</th><th>Value</th></tr>",
        f"<tr><td>Server name</td><td><pre>{server_name}</pre></td></tr>",
        f"<tr><td>Protocol version</td><td><pre>{req.proto}</pre></td></tr>",
        f"<tr><td>Method</td><td><pre>{req.method}</pre></td></tr>",
        f"<tr><td>Path</td><td><pre>{req.path}</pre></td></tr>",
        *[f"<tr><td>(Header) {kv[0]}</td><td><pre>{kv[1]}</pre></td></tr>" for kv in req.headers.items()],
        "</table></body></html>",
    ])
    return make_html(req.proto, Status.OK, None, dict(), res)


def get_status_line(resp: Response) -> str:
    add = f" - {resp.code_str}" if resp.code_str else ''
    proto = resp.proto if resp.proto <= 'HTTP/1.0' else 'HTTP/1.0'
    return f"{proto} {resp.code.value} {resp.code}{add}\r\n"


async def response_sender(writer: asyncio.StreamWriter, resp: Response) -> None:
    data: list[bytes] = []
    if resp.proto != 'HTTP/0.9':
        # TODO proper CRLF encode!!
        data.append(get_status_line(resp).encode('utf8'))
        data.extend(
            f"{key}: {value}\r\n".encode('utf8') for key, value in resp.headers.items()
        )
        data.append(b'\r\n')

    if isinstance(resp.body, str):
        data.append(resp.body.encode('utf8'))
    else:
        data.append(resp.body)

    writer.write(b''.join(data))
    await writer.drain()


async def server(
    host: str = '0.0.0.0',
    port: int = 8008,
    request_handler: typing.Callable[[Request], typing.Awaitable[Response]] = request_handler
) -> None:
    async def server_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        req = await parse_request(reader)
        if isinstance(req, Request):
            resp = await request_handler(req)
            logging.info(f"{req.method} {req.path.path} {req.proto} -> {get_status_line(resp).strip()}")
        else:
            resp = req
            logging.info(f"-> {get_status_line(resp).strip()}")

        await response_sender(writer, resp)

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

