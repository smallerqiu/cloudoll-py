document.addEventListener('DOMContentLoaded', function () {
    // websocket
    let ws = new WebSocket('ws://localhost:9001/ws');
    let refws = document.querySelector('.ws-msg-list');
    ws.onopen = function (evt) {
        console.log("ws connected...");
        refws.innerHTML += 'connected...\n';
    };
    ws.onmessage = function (evt) {
        console.log("Received Message: " + evt.data);
        refws.innerHTML += 'message:' + evt.data + '\n';
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
            headers: {},
        }
        let data = {
            name: 'cloudoll',
            age: 18
        }
        try {
            let dataInput = document.querySelector('#api-request');
            if (dataInput.innerHTML.trim()) {
                data = JSON.parse(dataInput.innerHTML);
            }
        } catch (e) {
            console.log(document.querySelector('#api-request').innerHTML)
            return;
        }
        if (method === 'post' || method === 'put') {
            options.body = JSON.stringify(data)
            options.headers['Content-Type'] = 'application/json';
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
    btnLogin = document.querySelector('.btn-login');
    btnLogin.onclick = function () {
        let username = document.getElementById('account').value;
        let password = document.getElementById('password').value;
        let result = document.querySelector('.login-result');
        let url = '/api/account/login';
        let options = {
            method: 'post',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                account: username,
                password: password
            })
        };
        fetch(url, options)
            .then(async (r) => {
                let json = await r.json();
                if (r.ok) {
                    result.innerHTML = JSON.stringify(json, null, 4);
                } else {
                    result.innerHTML = json.message || 'login failed';
                }
            })
            .catch((err) => {
                result.innerHTML = err.message || 'login failed';
            });
    }
    // upload
    btnUpload = document.querySelector('.btn-upload');
    btnUpload.onclick = function () {
        let fileInput = document.querySelector('input[type="file"]');
        let formData = new FormData();
        formData.append('file', fileInput.files[0]);
        if (!fileInput.files.length) {
            alert('please select a file to upload');
            return;
        }
        let result = document.querySelector('.upload-result');
        result.innerHTML = 'uploading...';
        fetch('/api/upload', {
            method: 'post',
            body: formData
        }).then(async (r) => {
            let json = await r.json();
            if (r.ok) {
                result.innerHTML = JSON.stringify(json, null, 4);
            } else {
                result.innerHTML = json.message || 'upload failed';
            }
        }).catch((err) => {
            result.innerHTML = err.message || 'upload failed';
        });
    }

})
