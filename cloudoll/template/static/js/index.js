document.addEventListener('DOMContentLoaded', function () {
    // websocket
    let ws = new WebSocket('ws://localhost:9001/ws');
    let refws = document.querySelector('.ws-msg-list');
    ws.onopen = function (evt) {
        console.log("ws connected...");
        refws.innerHTML += '已连接...\n';
    };
    ws.onmessage = function (evt) {
        console.log("Received Message: " + evt.data);
        refws.innerHTML += '消息:' + evt.data + '\n';
    };
    ws.onerror = function (evt) {
        console.log('Error ', evt);
    };
    ws.onclose = function (evt) {
        console.log('ws closed.');
    };

    // send ws msg
    let wsbtn = document.querySelector('.ws-btn');
    wsbtn.onclick = function () {
        let input = document.querySelector('.ws-input')
        let msg = input.value;
        if (msg.trim()) {
            ws.send(msg);
            input.value = '';
        }
    };

    // eventsource
    let esbtn = document.querySelector('.es-btn');
    let startES = function () {
        let es = new EventSource('/es');
        es.onmessage = function (evt) {
            document.querySelector('.es-msg-list').innerHTML += evt.data + '\n';
            esbtn.setAttribute('disabled', 'disabled')
        };
        es.onerror = function (evt) {
            es.close()
            esbtn.removeAttribute('disabled')
            console.log('es closed');
        };
        es.onopen = function (evt) {
            console.log('es connected');
        };
    };

    startES();
    // send es
    esbtn.onclick = function () {
        startES()
    }


    // api
    document.querySelector('.btn-api').onclick = function () {
        let url = document.getElementById('api-url').value
        let method = document.getElementById('api-method').value
        let controller = new AbortController();
        let options = {
            method: method,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json'
            },
        }
        let data = {
            name: 'cloudoll',
            age: 18
        }
        if (method === 'post' || method === 'put') {
            options.body = JSON.stringify(data)
        } else {
            let { search } = new URL(url);
            url += (search ? "&" : "?") + new URLSearchParams(data).toString();
        }
        let result = document.querySelector('#api-result');
        fetch(url, options)
            .then(async (r) => {
                if (r.ok) {
                    return r.json();
                } else {
                    if (r.status == 401) {
                        // todo
                    }
                    if (r.status == 400) {
                        let res = await r.json();
                        throw new Error(res.message);
                    } else {
                        try {
                            let res = await r.json();
                            return res
                        } catch (e) {
                            // console.log(e)
                            throw new Error(r.statusText || "Something went wrong");
                        }
                    }
                }
            })
            .then((data) => {
                // console.log(data);
                result.innerHTML = JSON.stringify(data, null, 4);
            })
            .catch((err) => {
                result.innerHTML = err;
                // console.log(err.message)
            })
            .finally(() => {
                // todo
            });
    }


    // login

    // upload



})
