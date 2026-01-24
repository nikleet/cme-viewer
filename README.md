## Local run

```bash
python -m app.server --mode local --data-dir .
```
Browser opens automatically.

## Remote run (SSH tunnel)

### On local machine
```
ssh -L 8080:localhost:8080 user@q.predsci.com
```

### On server
```
./scripts/start_server.sh /path/to/data
```

Open in browser:
```
http://localhost:8080
```

