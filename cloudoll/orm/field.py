class objdict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


OP = objdict(
    AND="AND",
    OR="OR",
    ADD="+",
    SUB="-",
    MUL="*",
    DIV="/",
    BIN_AND="&",
    BIN_OR="|",
    XOR="#",
    MOD="%",
    EQ="=",
    LT="<",
    LTE="<=",
    GT=">",
    GTE=">=",
    NE="!=",
    IN="IN",
    NOT_IN="NOT IN",
    IS="IS",
    DESC="DESC",
    ASC="ASC",
    AVG="AVG",
    AS="AS",
    SUM="SUM",
    DATE_FORMAT="DATE_FORMAT",
    JSON_CONTAINS_OBJECT="JSON_CONTAINS_OBJECT",
    JSON_CONTAINS_ARRAY="JSON_CONTAINS_ARRAY",
    COUNT="COUNT",
    COUNT_WHEN="COUNT_WHEN",
    IS_NOT="IS NOT",
    IS_NOT_NULL="IS NOT NULL",
    IS_NULL="IS NULL",
    LIKE="LIKE",
    NOT_LIKE="NOT LIKE",
    ILIKE="ILIKE",
    BETWEEN="BETWEEN",
    CONTAINS="CONTAINS",
    NOT_BETWEEN="NOT BETWEEN",
    REGEXP="REGEXP",
    IREGEXP="IREGEXP",
    DISTINCT="DISTINCT",
    CONCAT="||",
    BITWISE_NEGATION="~",
)


class FieldBase:
    def _op(op, inverse=False):
        def inner(self, rhs):
            if inverse:
                return Expression(rhs, op, self)
            return Expression(self, op, rhs)

        return inner

    def __eq__(self, rhs):
        return Expression(self, OP.EQ, rhs)

    def __ne__(self, rhs):
        return Expression(self, OP.NE, rhs)

    __lt__ = _op(OP.LT)  # <
    __le__ = _op(OP.LTE)  # <=
    __gt__ = _op(OP.GT)  # >
    __ge__ = _op(OP.GTE)  # >=
    __and__ = _op(OP.AND)  # and
    __or__ = _op(OP.OR)  # or

    # 运算
    __add__ = _op(OP.ADD)  # +
    __radd__ = _op(OP.ADD, True)  # +=
    __sub__ = _op(OP.SUB)  # -
    __rsub__ = _op(OP.SUB, True)  # -=
    __mul__ = _op(OP.MUL)  # *
    __rmul__ = _op(OP.MUL, True)  # *=
    __div__ = _op(OP.DIV)  # /
    __rdiv__ = _op(OP.DIV, True)  # /=

    In = _op(OP.IN)  # in
    not_in = _op(OP.NOT_IN)  # not in
    like = _op(OP.LIKE)  # like
    ilike = _op(OP.ILIKE)  # ilike for pg
    not_like = _op(OP.NOT_LIKE)  # not like

    def distinct(self, *arg):
        return Expression(self, OP.DISTINCT, arg)

    def desc(self):
        return Expression(self, OP.DESC, None)

    def asc(self):
        return Expression(self, OP.ASC, None)

    def count(self):
        return Function(self, OP.COUNT)

    def count_when(self, value):
        return Function(self, OP.COUNT_WHEN, value)

    def sum(self):
        return Function(self, OP.SUM)

    def avg(self):
        return Function(self, OP.AVG)

    def date_format(self, args):
        return Function(self, OP.DATE_FORMAT, args)

    def json_contains_object(self, key, value):
        return Function(self, OP.JSON_CONTAINS_OBJECT, (key, value))

    def json_contains_array(self, args):
        return Function(self, OP.JSON_CONTAINS_ARRAY, args)

    def contains(self, args):
        return Function(self, OP.CONTAINS, args)
        # return AO(f"contains({self.full_name},?)", args)

    def As(self, args):
        return Expression(self, OP.AS, args)

    def is_null(self):
        return Expression(self, OP.IS_NULL, None)

    def not_null(self):
        return Expression(self, OP.IS_NOT_NULL, None)

    def between(self, h1, h2):
        return Expression(self, OP.BETWEEN, ExpList(h1, OP.AND, h2))

    def not_between(self, h1, h2):
        return Expression(self, OP.NOT_BETWEEN, ExpList(h1, OP.AND, h2))


class ExpList(FieldBase):
    def __init__(self, lpt, op, rpt):
        self.lpt = lpt
        self.op = op
        self.rpt = rpt

    def sql(self):
        lpt = self.lpt
        rpt = self.rpt

        p = []
        q = []
        if isinstance(lpt, Exception):
            _q, _p = lpt.sql()
            q = q + _q
            p = p + _p
        else:
            q.append("?")
            p.append(lpt)
        q.append(f" {self.op} ")
        if isinstance(rpt, Exception):
            _q, _p = lpt.sql()
            q = q + _q
            p = p + _p
        else:
            q.append("?")
            p.append(lpt)

        return "".join(q), p
        # return f"{lpt.sql() if isinstance(lpt,Expression) else lpt} {self.op} {rpt.sql() if isinstance(rpt,Expression) else rpt}"


class Function(FieldBase):
    def __init__(self, col, op, rpt=None):
        self.col = col
        self.op = op
        self.rpt = rpt

    def sql(self):
        op = self.op
        col_name = self.col.full_name
        is_field = isinstance(self.rpt, Field)
        # todo:
        if op == OP.DATE_FORMAT:
            return f"{op}({col_name},?)", [self.rpt]
        elif op == OP.JSON_CONTAINS_OBJECT:
            _k, _v = self.rpt
            key = _k.full_name if isinstance(_k, Field) else f"'{_k}'"
            return f"json_contains({col_name},json_object({key},?))", [_v]
        elif op == OP.JSON_CONTAINS_ARRAY:
            if is_field:
                return (
                    f"json_contains({col_name},json_array({self.rpt.full_name}))",
                    None,
                )
            return f"json_contains({col_name},json_array(?))", [self.rpt]
        elif op == OP.COUNT:
            return f"COUNT({col_name})", None
        elif op == OP.COUNT_WHEN:
            return f"COUNT(CASE WHEN {col_name} = ? THEN 1 END)", [self.rpt]


class Expression(FieldBase):
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        # self.__value = ""
        # if op in "+-*/|&~" and lhs._value:
        #     cal = f"{lhs._value}{op}"
        #     if isinstance(rhs, FieldBase):
        #         self.__value = str(eval(f"{cal}{rhs._value}"))
        #     else:
        #         self.__value = str(eval(f"{cal}{rhs}"))

    def sql(self):
        l = self.lhs
        r = self.rhs
        is_fun = isinstance(l, Function)
        p = []
        q = []
        if not is_fun:
            q.append("(")
        if isinstance(l, Field):
            q.append(l.full_name)
        elif isinstance(l, Expression):
            _q, _p = l.sql()
            q.append(_q)
            p = p + _p
        elif is_fun:
            _q, _p = l.sql()
            q.append(_q)
            if _p:
                p = p + _p
            # return l.sql()

        q.append(f" {self.op} ")

        if isinstance(r, Field):
            if r._value is not None:
                # _value = r._value if r._value is not None else r.full_name
                q.append("?")
                p.append(r._value)
            else:
                q.append(r.full_name)
            # q.append(str(r._value) if r._value is not None else r.full_name)
        elif isinstance(r, FieldBase):
            _q, _p = r.sql()
            q.append(_q)
            p = p + _p
        elif self.op == OP.AS:
            # is_fun or (isinstance(r, str) and (self.op == OP.AND or self.op == OP.OR)):
            q.append(r)
        elif r is not None:
            q.append("?")
            p.append(r)
        if not is_fun:
            q.append(")")
        # q.append(")")
        q = [str(num) for num in q]
        # print("".join(q))
        return "".join(q), p

    # def __str__(self):
    #     return self.__value
    #     cal = f"{self.lhs._value}{self.op}"
    #     if isinstance(self.rhs, FieldBase):
    #         return str(eval(f"{cal}{self.rhs._value}"))
    #     return str(eval(f"{cal}{self.rhs}"))

    def __repr__(self):
        # return self.__value
        cal = f"{self.lhs.value}{self.op}"
        if isinstance(self.rhs, FieldBase):
            return str(eval(f"{cal}{self.rhs.value}"))
        return str(eval(f"{cal}{self.rhs}"))


class Field(FieldBase):
    def __init__(
        self,
        name,  # 列名
        column_type,  # 类型
        default=None,  # 默认值
        primary_key=False,  # 主键
        charset=None,  # 编码
        max_length=None,  # 长度
        auto_increment=False,  # 自增
        NOT_NULL=False,  # 非空
        created_generated=False,  # 创建时for datetime
        update_generated=False,  # 更新时for datetime
        unsigned=False,  # 无符号，没有负数
        comment=None,  # 备注
        **kwargs,
    ):
        super().__init__()
        self.full_name = None
        self._value = None
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.charset = charset
        self.default = default
        self.max_length = max_length
        self.auto_increment = auto_increment
        self.NOT_NULL = NOT_NULL
        self.created_generated = created_generated
        self.update_generated = update_generated
        self.comment = comment
        self.unsigned = unsigned

    def __str__(self):
        return str(self._value)
        # "<%s, %s:%s>" % (self.__class__.__name__, self.column_type, self.name)
        # return self.name

    def __repr__(self):
        return str(self._value)

    # def __getattr__(self, item):
    #     return self[item]
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value