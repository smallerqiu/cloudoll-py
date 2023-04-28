let socket = new WebSocket("ws://localhost:9001/ws");

// 建立连接
socket.onopen = () => {
    console.log("connection");
    //发送消息,告诉服务器,我上线了.
    socket.send(JSON.stringify({name: "chuchur", msg: "我来了", time: Date.now()}));
};
//接收消息
socket.onmessage = (evt) => {
    let data = evt.data;
    console.log(data);
};

//socket 断开
socket.onclose = () => {
    console.log("close");
};
//socket 发生错误
socket.onerror = () => {
    console.log("error");
};
