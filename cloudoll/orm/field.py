class objdict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


OP = objdict(
    AND='AND',
    OR='OR',
    ADD='+',
    SUB='-',
    MUL='*',
    DIV='/',
    BIN_AND='&',
    BIN_OR='|',
    XOR='#',
    MOD='%',
    EQ='=',
    LT='<',
    LTE='<=',
    GT='>',
    GTE='>=',
    NE='!=',
    IN='IN',
    NOT_IN='NOT IN',
    IS='IS',
    DESC='DESC',
    ASC='ASC',
    AVG='AVG',
    AS='AS',
    SUM='SUM',
    COUNT='COUNT',
    IS_NOT='IS NOT',
    IS_NOT_NULL='IS NOT NULL',
    IS_NULL='IS NULL',
    LIKE='LIKE',
    NOT_LIKE='NOT LIKE',
    ILIKE='ILIKE',
    BETWEEN='BETWEEN',
    CONTAINS='CONTAINS',
    NOT_BETWEEN='NOT BETWEEN',
    REGEXP='REGEXP',
    IREGEXP='IREGEXP',
    DISTINCT='DISTINCT',
    CONCAT='||',
    BITWISE_NEGATION='~')


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
    __sub__ = _op(OP.SUB, True)  # -=
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

    def sum(self):
        return Function(self, OP.SUM)

    def avg(self):
        return Function(self, OP.AVG)

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
            q = q+_q
            p = p+_p
        else:
            q.append("?")
            p.append(lpt)
        q.append(f" {self.op} ")
        if isinstance(rpt, Exception):
            _q, _p = lpt.sql()
            q = q+_q
            p = p+_p
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
        # todo:
        return f"{self.op}({self.col.full_name} {','+str(self.rpt) if self.rpt else ''})"


class Expression(FieldBase):
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs

    def sql(self):
        l = self.lhs
        r = self.rhs
        p = []
        q = ["("]
        if isinstance(l, Field):
            q.append(l.full_name)
        elif isinstance(l, Expression):
            _q, _p = l.sql()
            q.append(_q)
            p = p+_p
        q.append(f" {self.op} ")

        if isinstance(r, Field):
            q.append(r.full_name)
        elif isinstance(r, FieldBase):
            _q, _p = r.sql()
            q.append(_q)
            p = p+_p
        else:
            q.append('?')
            p.append(r)
        q.append(')')
        return "".join(q), p
        # return f"({l.full_name if isinstance(l,Field) else l.sql()} {self.op} {r.full_name if isinstance(r,Field) else (r.sql() if isinstance(r,FieldBase) else str(r))})"


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

    # def __getattr__(self, item):
    #     return self[item]

    def set_value(self, value):
        self._value = value

    def get_value(self):
        return self._value
