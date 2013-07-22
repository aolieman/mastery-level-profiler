Array.prototype.remove = function() {
    var what, a = arguments, L = a.length, ax;
    while (L && this.length) {
        what = a[--L];
        while ((ax = this.indexOf(what)) !== -1) {
            this.splice(ax, 1);
        }
    }
    return this;
};

var app = angular.module('reviewApp',['ui.slider', 'ui.bootstrap']);

app.controller("StatementCtrl", function ($scope, $http) {
    $scope.initdata = function() {
        $http.get('/statements?December=50bbb').success(function(response){
            $scope.pseudo = response['pseudo'];
            $scope.extracted = response['extracted'];

            $scope.inferred = response['inferred'];
            angular.forEach($scope.extracted, function(value, key){
                value.correct = true;
            });


        });
    };

    /* Toggle the correctness of a topic */
    $scope.toggleCorrect = function(value){
        value.correct = !value.correct;
    };

    /* Return only correct statements */
    $scope.filterCorrect = function(statements){
        var out_statements = [];
        for(obj in statements) {
            if (statements[obj].correct) {
                out_statements.push(statements[obj]);
            }
        }
        return out_statements;
    };
    /* Pagination */
    $scope.currentPage = 0;
    $scope.pageSize = 12;
    $scope.numberOfPages = function(statements){
        return Math.ceil($scope.filterCorrect(statements).length/$scope.pageSize);
    };

    /* Add missing statements */
    $scope.getSkills = function(value) {
        return $http.get('/skill?query=' + value).then(function(response){
            return response.data.resultList;
        });
    };
    $scope.missing = [];
    $scope.addMissing = function(toadd){
        $scope.missing.push(toadd);
    };
    $scope.delMissing = function(todelete){
        $scope.missing.remove(todelete);
    };

    /* Save reviewed statements / topics */
    $scope.toConsole = function(){
        var postjson = {'extracted': $scope.extracted, 'missing': $scope.missing};
        console.log(postjson);
        $http.post('/reviewed.json', postjson).success(function(response){
            console.log("POSTed something")
        });
    };

    $scope.todos = [
        {text:'Learn AngularJS', done:false},
        {text:'Build an app', done:false}
    ];

    $scope.getTotalTodos = function () {
        return $scope.todos.length;
    };

    $scope.clearCompleted = function () {
        $scope.todos = _.filter($scope.todos, function(todo){
            return !todo.done;
        });
    };

    $scope.addTodo = function () {
        $scope.todos.push({text:$scope.formTodoText, done:false});
        $scope.formTodoText = '';
    };
});

// A startFrom filter
app.filter('startFrom', function() {
    return function(input, start) {
        start = +start; //parse to int
        return input.slice(start);
    }
});